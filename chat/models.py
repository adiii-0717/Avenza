from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Message(models.Model):
    sender   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sender')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receiver')
    message  = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} → {self.receiver}"


class UserProfile(models.Model):
    """
    Extends the built-in User with a display name and profile photo.
    A profile is created automatically for every new User via a signal.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    display_name = models.CharField(
        max_length=40,
        blank=False,
        help_text="Friendly name shown in chat. Falls back to username if empty."
    )
    profile_photo = models.ImageField(
        upload_to='profile_photos/',
        null=True,
        blank=True,
        help_text="Optional profile picture. Leave blank to use initials."
    )

    def __str__(self):
        return f"Profile({self.user.username})"

    def get_display_name(self):
        """Return display_name if set, otherwise fall back to username."""
        return self.display_name.strip() or self.user.username

    def get_photo_url(self):
        """Return photo URL if a photo exists, otherwise None."""
        if self.profile_photo:
            return self.profile_photo.url
        return None


# ── Signals ──────────────────────────────────────────────────────────────────
# Automatically create / sync a UserProfile whenever a User is saved.

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Guard: profile may not exist yet for legacy users — get_or_create is safe.
    UserProfile.objects.get_or_create(user=instance)