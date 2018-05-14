from bs4 import BeautifulSoup
import datetime
import requests

from django.conf import settings
from django.utils import timezone

from urllib.parse import urlparse

from .errors import Disallowed, DisallowedInRobotsTxt, UnableToConnect
from .models import Domain, Url


CRAWLER_ALLOWED_URLS = getattr(settings, 'CRAWLER_ALLOWED_URLS', [])
CRAWLER_DISALLOWED_URLS = getattr(settings, 'CRAWLER_DISALLOWED_URLS', [])
CRAWLER_MINIMUM_CRAWL_INTERVAL = getattr(settings, 'CRAWLER_MINIMUM_CRAWL_INTERVAL', datetime.timedelta(hours=8))
CRAWLER_USERAGENT = getattr(settings, 'CRAWLER_USERAGENT', 'django_webcrawler')


def is_crawlable_url(url):
    for url_re in CRAWLER_DISALLOWED_URLS:
        if url_re.match(url):
            return False
    for url_re in CRAWLER_ALLOWED_URLS:
        if url_re.match(url):
            return True
    return False


def add_url(url):
    if not is_crawlable_url(url):
        raise Disallowed('Crawling this URL is not allowed!')
    if not Url.objects.filter(url=url).exists():
        url_parsed = urlparse(url)
        domain = Domain.objects.get_or_create(hostname=url_parsed.netloc)[0]
        if not domain.is_allowed_in_robots_txt(url):
            raise DisallowedInRobotsTxt(url)
        return Url.objects.create(url=url, domain=domain)


def crawl_url(url):
    # Make sure crawling is allowed
    if not is_crawlable_url(url.url):
        raise Disallowed('Crawling this URL is not allowed!')
    if not url.domain.is_allowed_in_robots_txt(url.url):
        raise DisallowedInRobotsTxt(url.url)

    url_parsed = urlparse(url.url)

    # Fetch URL
    headers = {'User-Agent': CRAWLER_USERAGENT}
    try:
        response = requests.get(url.url, headers=headers)
    except requests.exceptions.ConnectionError:
        raise UnableToConnect()

    # In case of errors, ignore this URL
    if response.status_code < 200 or response.status_code > 299:
        raise UnableToConnect()

    # Skip unsupported content types
    content_type = response.headers['content-type'].split(';')[0]
    if content_type != 'text/html':
        raise UnsupportedContentType('Content-type "{}" is not supported!'.format(response.headers['content-type']))

    # Parse content
    soup = BeautifulSoup(response.text, 'html.parser')

    # Parse links
    for link in soup.find_all('a'):
        link_url = link.get('href')

        # If there is no link for some reason
        if not link_url:
            continue

        link_url_parsed = urlparse(link_url)

        # Convert link URL to absolute format
        if not link_url_parsed.scheme:
            link_url_parsed = link_url_parsed._replace(scheme=url_parsed.scheme)
        if not link_url_parsed.netloc:
            link_url_parsed = link_url_parsed._replace(netloc=url_parsed.netloc)
        link_url = link_url_parsed.geturl()

        # Skip links that are not allowed
        if not is_crawlable_url(link_url):
            continue

        # Skip unsupported schemes
        if link_url_parsed.scheme not in ['http', 'https']:
            continue

        # Skip if disallowed in robots.txt
        link_domain = Domain.objects.get_or_create(hostname=link_url_parsed.netloc)[0]
        if not link_domain.is_allowed_in_robots_txt(link_url):
            continue

        link_url_object = Url.objects.get_or_create(url=link_url, defaults={'domain': link_domain})[0]

        url.links_to.add(link_url_object)

    # Update Url
    url.content = response.text
    url.visited_at = timezone.now()
    url.save(update_fields=['visited_at', 'content'])

    # Update Domain
    url.domain.visited_at = timezone.now()
    url.domain.save(update_fields=['visited_at'])


def crawl_random_url(clean_disallowed_urls=False):
    while True:

        # Try to get URL that is not visited lately
        url = Url.objects.filter(visited_at__isnull=True, domain__visited_at__isnull=True).first()
        if not url:
            url = Url.objects.filter(visited_at__isnull=True).order_by('domain__visited_at').first()
            if not url:
                url = Url.objects.filter(visited_at__lt=timezone.now() - CRAWLER_MINIMUM_CRAWL_INTERVAL).order_by('visited_at', 'domain__visited_at').first()

        if not url:
            break

        try:
            crawl_url(url)
            return url
        except Disallowed:
            if clean_disallowed_urls:
                url.delete()
            else:
                raise
        except DisallowedInRobotsTxt:
            if clean_disallowed_urls:
                url.delete()
            else:
                url.visited_at = timezone.now()
                url.save(update_fields=['visited_at'])
                url.domain.visited_at = timezone.now()
                url.domain.save(update_fields=['visited_at'])
        except UnableToConnect:
            url.visited_at = timezone.now()
            url.save(update_fields=['visited_at'])
            url.domain.visited_at = timezone.now()
            url.domain.save(update_fields=['visited_at'])

    return None
