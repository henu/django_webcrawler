import datetime
import hashlib
import re
import requests
from urllib.parse import urlparse

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.dispatch import receiver


CRAWLER_USERAGENT = getattr(settings, 'CRAWLER_USERAGENT', 'django_webcrawler')


USERAGENT_RE = re.compile(r'^user-agent: ?(?P<useragent>\S+)$', re.IGNORECASE)
ALLOW_RE = re.compile(r'^allow: ?(?P<path>\S+)$', re.IGNORECASE)
DISALLOW_RE = re.compile(r'^disallow: ?(?P<path>\S+)$', re.IGNORECASE)


class Domain(models.Model):
    hostname = models.CharField(max_length=255, unique=True)

    visited_at = models.DateTimeField(null=True, blank=True, default=None)

    robots_txt = models.TextField(null=True, blank=True, default=None)
    robots_txt_updated_at = models.DateTimeField(null=True, blank=True, default=None)

    def is_allowed_in_robots_txt(self, url):
        url_parsed = urlparse(url)

        if url_parsed.netloc != self.hostname:
            raise Exception('URL is from wrong domain!')

        for line in self.get_robots_txt():
            rule, path = line.split(' ')
            if rule == 'Allow:':
                if url_parsed.path.startswith(path):
                    return True
            if rule == 'Disallow:':
                if url_parsed.path.startswith(path):
                    return False
            return True

    def get_robots_txt(self):
        # If not fetched recently, then fetch now
        if not self.robots_txt_updated_at or self.robots_txt_updated_at + datetime.timedelta(days=1) < timezone.now():
            self.robots_txt_updated_at = timezone.now()
            for scheme in ['https', 'http']:
                try:
                    response = requests.get('{}://{}/robots.txt'.format(scheme, self.hostname))
                except requests.exceptions.ConnectionError:
                    continue
                if response.status_code >= 200 and response.status_code <= 299:
                    robots_txt = []
                    current_user_agent = None
                    for line in response.text.split('\n'):
                        line = line.strip()
                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue
                        match = USERAGENT_RE.match(line) or ALLOW_RE.match(line) or DISALLOW_RE.match(line)
                        if match:
                            if match.re == USERAGENT_RE:
                                current_user_agent = match.groupdict()['useragent']
                            elif match.re == ALLOW_RE:
                                if current_user_agent in ['*', CRAWLER_USERAGENT]:
                                    robots_txt.append('Allow: ' + match.groupdict()['path'])
                            elif match.re == DISALLOW_RE:
                                if current_user_agent in ['*', CRAWLER_USERAGENT]:
                                    robots_txt.append('Disallow: ' + match.groupdict()['path'])
                    self.robots_txt = '\n'.join(robots_txt)
                    break
            self.save(update_fields=['robots_txt', 'robots_txt_updated_at'])
        if not self.robots_txt:
            return []
        return list(filter(None, self.robots_txt.split('\n')))

    def __str__(self):
        return self.hostname


class Url(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.URLField(max_length=5000)
    url_sha256 = models.CharField(max_length=64, unique=True)
    domain = models.ForeignKey(Domain, related_name='urls', on_delete=models.CASCADE)

    visited_at = models.DateTimeField(null=True, blank=True, default=None)

    content = models.TextField(null=True, blank=True, default=None)

    links_to = models.ManyToManyField('Url', related_name='linked_from')

    def __str__(self):
        return self.url


@receiver(models.signals.pre_save, sender=Url)
def set_url_sha256(sender, instance, *args, **kwargs):
    instance.url_sha256 = hashlib.sha256(instance.url.encode('utf8')).hexdigest()
