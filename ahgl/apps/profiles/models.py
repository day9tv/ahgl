import posixpath
import urllib2
import logging

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.utils.safestring import mark_safe
from django.template.defaultfilters import escape
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.template.defaultfilters import slugify

from social_auth.signals import socialauth_registered
from social_auth.backends.facebook import FacebookBackend
from social_auth.backends.pipeline import USERNAME

from idios.utils import get_profile_form
from pybb.models import PybbProfile
if "sorl.thumbnail" in settings.INSTALLED_APPS:
    from sorl.thumbnail import ImageField
else:
    from django.db.models import ImageField

from . import RACES
from .fields import HTMLField

logger = logging.getLogger(__name__)

class Profile(PybbProfile):
    user = models.ForeignKey(User, verbose_name=_("user"))
    name = models.CharField(_("name"), max_length=50)
    slug = models.SlugField(max_length=50, editable=False, unique=True) # TODO: make autogenerated slug field that points to the field it gets its sluggification from
    photo = ImageField(upload_to='profile_photos', null=True, blank=True)
    custom_thumb = ImageField(upload_to='profile_custom_thumb_photos', null=True, blank=True)
    #about = models.TextField(_("about"), null=True, blank=True)
    #location = models.CharField(_("location"), max_length=40, null=True, blank=True)
    website = models.URLField(_("website"), null=True, blank=True, verify_exists=False)
    questions_answers = HTMLField(tags=['ol','ul','li', 'strong', 'em', 'p'], blank=True)

    #starcraft data
    char_name = models.CharField(max_length=20, blank=True)
    char_code = models.PositiveSmallIntegerField(null=True, blank=True)
    bnet_profile = models.URLField(null=True, blank=True)
    race = models.CharField(max_length=1, choices=RACES, null=True, blank=True)

    #company data
    title = models.CharField(max_length=70, blank=True)
    
    @property
    def avatar(self):
        return self.thumbnail()
    
    @property
    def thumbnail(self):
        return self.custom_thumb or self.photo

    def is_active(self, tournament=None): #TODO: make this check if they are active in that particular tournament
        return self.user.is_superuser or self.teams.filter(tournament__active=True).count() > 0 or self.is_captain()
    
    def is_captain(self):
        return self.captain_of.filter(tournament__active=True).count() > 0
    
    def active_teams(self):
        return self.teams.filter(tournament__active=True).select_related('tournament')
    
    @property
    def wins(self):
        return self.game_wins.filter(match__published=True).count()
    @property
    def losses(self):
        return self.game_losses.filter(match__published=True).count()
    
    def __unicode__(self):
        return self.char_name or self.name or self.user.username
    
    @models.permalink
    def get_absolute_url(self, group=None):
        return ('profile_detail', (), {'slug': self.slug,
                                       }
                )

    @classmethod
    def get_form(cls):
        return get_profile_form(cls)

    def save(self, *args, **kwargs):
        """
        Based on the Tag save() method in django-taggit, this method simply
        stores a slugified version of the title, ensuring that the unique
        constraint is observed
        """
        self.slug = slug = slugify(self.name or self.user.username)
        i = 0
        while True:
            try:
                savepoint = transaction.savepoint()
                res = super(Profile, self).save(*args, **kwargs)
                transaction.savepoint_commit(savepoint)
                return res
            except IntegrityError:
                transaction.savepoint_rollback(savepoint)
                i += 1
                self.slug = '%s_%d' % (slug, i)

class Team(models.Model):
    """Per Tournament"""
    name = models.CharField(_("name"), max_length=50)
    slug = models.SlugField(max_length=50)
    photo = ImageField(upload_to='team_photos', null=True, blank=True)
    charity = models.ForeignKey('profiles.Charity', null=True, blank=True, on_delete=models.SET_NULL, related_name='teams')
    motto = models.CharField(max_length=70, blank=True)
    members = models.ManyToManyField('Profile', null=True, blank=True, related_name='teams')
    tournament = models.ForeignKey('tournaments.Tournament', related_name='teams', db_index=True)
    captain = models.ForeignKey('Profile', null=True, blank=True, on_delete=models.SET_NULL, related_name='captain_of')

    #computed
    rank = models.IntegerField()
    
    wins = models.IntegerField(default=0, editable=False)
    losses = models.IntegerField(default=0, editable=False)
    tiebreaker = models.IntegerField(default=0, editable=False)
    
    seed = models.IntegerField(default=0)
    
    def update_stats(self):
        self.wins = self.match_wins.filter(published=True).count()
        self.losses = self.match_losses.filter(published=True).count()
        self.tiebreaker = self.game_wins.filter(match__published=True).count() - self.game_losses.filter(match__published=True).count()
        self.save()
    
    def __unicode__(self):
        return self.name
    
    @models.permalink
    def get_absolute_url(self, tournament_slug=None):
        if not tournament_slug:
            tournament_slug = self.tournament.slug
        return ('team_page', (), {'tournament': tournament_slug,
                                  'slug': self.slug,
                                  }
                )
    
    class Meta:
        unique_together = (('name','tournament'),('slug', 'tournament'),)
        ordering = ('name',)

class Charity(models.Model):
    name = models.CharField(_("name"), max_length=50)
    desc = models.TextField(blank=True)
    link = models.URLField(blank=True)
    logo = ImageField(upload_to='charity_logos', null=True, blank=True)
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        ordering = ('name',)

@receiver(socialauth_registered, sender=FacebookBackend, dispatch_uid="tournaments_facebook_extra_values")
def facebook_extra_values(sender, user, response, details, **kwargs):
    for name, value in details.iteritems():
        # do not update username, it was already generated
        if name == USERNAME:
            continue
        if value and value != getattr(user, name, None):
            setattr(user, name, value)
    
    profile = user.get_profile()
    profile.name = response.get('name')
    if not profile.photo:
        url = 'http://graph.facebook.com/%s/picture?type=large' % response.get('id')
        try:
            content = urllib2.urlopen(url)
            # Facebook default image check
            if sender.name == 'facebook' and 'image/gif' in str(content.info()):
                return
     
            filename = user.username + "_profile" + '.' + content.headers.subtype
            profile.photo.save(filename, ContentFile(content.read()))
        except IOError, e:
            logger.debug(e)
    try:
        profile.language = response.get('locale').split("_")[0]
        profile.full_clean()
    except Exception:
        pass
    profile.time_zone = response.get('timezone')
    profile.save()
    #EmailAddress(user=user, email=user.email, verified=True, primary=True).save() TODO: add email address as possible
    """account = user.account_set.all()[0]
    account.language = response.get('locale')
    #account.timezone = coerce_timezone_value(str(response.get('timezone')))
    account.save() TODO: Import language and timezone"""
    return True
