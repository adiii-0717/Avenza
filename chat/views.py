import os
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Message, UserProfile
from django.db.models import Q


def get_room_name(user1, user2):
    return "_".join(sorted([user1, user2]))


# ── Home ──────────────────────────────────────────────────────────────────────

def chat_home(request):
    if not request.user.is_authenticated:
        return redirect('login')

    # Get users with whom current user has chatted
    chatted_users = User.objects.filter(
        Q(sender__receiver=request.user) | Q(receiver__sender=request.user)
    ).distinct()

    return render(request, 'chat.html', {
        'users': chatted_users
    })


# ── Register ──────────────────────────────────────────────────────────────────

def register_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        display_name = request.POST.get('display_name')  # ✅ THIS WAS MISSING

        if User.objects.filter(username=username).exists():
            return render(request, 'register.html', {
                'error': 'Username already exists'
            })

        user = User.objects.create_user(
            username=username,
            password=password
        )

        # ✅ SAVE DISPLAY NAME IN PROFILE
        user.profile.display_name = display_name
        user.profile.save()

        return redirect('login')

    return render(request, 'register.html')


# ── Login ─────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect('chat')

    return render(request, 'login.html')


# ── Private chat ──────────────────────────────────────────────────────────────

def private_chat(request, username):
    if not request.user.is_authenticated:
        return redirect('login')

    other_user = User.objects.get(username=username)
    room_name  = get_room_name(request.user.username, other_user.username)

    if request.method == 'POST':
        msg = request.POST.get('message')
        if msg:
            Message.objects.create(
                sender=request.user,
                receiver=other_user,
                message=msg
            )

    messages = Message.objects.filter(
        sender=request.user, receiver=other_user
    ) | Message.objects.filter(
        sender=other_user, receiver=request.user
    )
    messages = messages.order_by('timestamp')

    users = User.objects.filter(
    Q(sender__receiver=request.user) | Q(receiver__sender=request.user)).distinct()

    return render(request, 'chat.html', {
        'chat_user': other_user,
        'messages':  messages,
        'users':     users,
        'room_name': room_name,
    })


# ── Logout ────────────────────────────────────────────────────────────────────

def logout_view(request):
    logout(request)
    return redirect('login')


# ── Profile update ────────────────────────────────────────────────────────────

def _broadcast_profile(user, profile):
    """
    Push a profile_update event to every connected WebSocket via the
    'everyone' channel-layer group so all open browser tabs update instantly.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'everyone',
        {
            'type':         'profile.update',   # dots → underscores = handler name
            'username':     user.username,
            'display_name': profile.get_display_name(),
            'photo_url':    profile.get_photo_url(),
        },
    )


@login_required
@require_POST
def update_profile(request):
    """
    POST /profile/update/

    action=save   → update display_name and/or replace profile_photo
    action=remove → delete the existing profile_photo

    Returns JSON. After every successful write, broadcasts a profile_update
    event to all connected sockets via the 'everyone' channel-layer group.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    action      = request.POST.get('action', 'save')

    # ── Remove photo ──────────────────────────────────────────────────────────
    if action == 'remove':
        if profile.profile_photo:
            if os.path.isfile(profile.profile_photo.path):
                os.remove(profile.profile_photo.path)
            profile.profile_photo = None
            profile.save(update_fields=['profile_photo'])

        _broadcast_profile(request.user, profile)
        return JsonResponse({
            'status':       'ok',
            'photo_url':    None,
            'display_name': profile.get_display_name(),
        })

    # ── Save display name + optional new photo ────────────────────────────────
    display_name = request.POST.get('display_name', '').strip()

    if len(display_name) > 40:
        return JsonResponse({
            'status':  'error',
            'message': 'Display name is too long (max 40 characters).',
        }, status=400)

    profile.display_name = display_name

    if 'profile_photo' in request.FILES:
        new_photo     = request.FILES['profile_photo']
        allowed_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

        if new_photo.content_type not in allowed_types:
            return JsonResponse({
                'status':  'error',
                'message': 'Unsupported image type. Please use JPEG, PNG, GIF or WebP.',
            }, status=400)

        if new_photo.size > 5 * 1024 * 1024:
            return JsonResponse({
                'status':  'error',
                'message': 'Image must be under 5 MB.',
            }, status=400)

        # Delete the old file from disk before saving the new one
        if profile.profile_photo:
            if os.path.isfile(profile.profile_photo.path):
                os.remove(profile.profile_photo.path)

        profile.profile_photo = new_photo

    profile.save()
    _broadcast_profile(request.user, profile)

    return JsonResponse({
        'status':       'ok',
        'display_name': profile.get_display_name(),
        'photo_url':    profile.get_photo_url(),
    })

def search_users(request):
    query = request.GET.get('q')

    users = User.objects.filter(
        username__icontains=query
    ).exclude(username=request.user.username)[:10]

    data = list(users.values('username'))

    return JsonResponse({'users': data})