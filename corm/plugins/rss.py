import datetime
import re
import requests
from xml.etree import ElementTree as XMLParser
from html.parser import HTMLParser
import io

from corm.plugins import BasePlugin, PluginImporter
from corm.models import *

class RssLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rss_links = dict()

    def handle_starttag(self, tag, attrs):
        #<link rel="alternate" type="application/rss+xml" title="InfluxData &raquo; Feed" href="https://www.influxdata.com/feed/" />
        if tag == 'link':
            link = dict()
            for key, value in attrs:
                link[key] = value
            if 'type' in link and link['type'] == "application/rss+xml":
                self.rss_links[link['href']] = link['title']


class RssPlugin(BasePlugin):

    def get_source_type_name(self):
        return "RSS"

    def get_import_command_name(self):
        return "rss"

    def get_source_importer(self, source):
        return RssImporter(source)

    def get_channels(self, source):
        channels = []

        resp = requests.get(source.server)   
        if resp.status_code == 200:
            data = resp.text
            parser = RssLinkParser()
            parser.feed(data)
            i = 0
            for url, title in parser.rss_links.items():
                channels.append({
                    'id': url,
                    'name': title,
                    'topic': "",
                    'count': i,
                })
                i += 1
        else:
            print("Request failed: %s" % resp.content)
        return channels

class RssImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%a, %d %b %Y %H:%M:%S %z'
        self.BLOG_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Blog Post")

    def import_channel(self, channel):
      source = channel.source
      community = source.community

      resp = requests.get(channel.origin_id)
      if resp.status_code == 200:
          rawxml = io.StringIO(resp.text)
          tree = XMLParser.parse(rawxml)
          for feedchannel in tree.findall('channel'):
              for item in feedchannel.findall('item'):
                origin_id = item.find('guid').text
                tstamp = self.strptime(item.find('pubDate').text)
                author_name = item.find('{http://purl.org/dc/elements/1.1/}creator').text
                article_title = item.find('title').text
                article_link = item.find('link').text
                blog_author_id = '%s/%s' % (source.server, author_name)
                contact_matches = Contact.objects.filter(origin_id=blog_author_id, source=source)
                if contact_matches.count() == 0:
                    member = Member.objects.create(community=community, name=author_name, date_added=tstamp)
                    contact, created = Contact.objects.get_or_create(origin_id=blog_author_id, defaults={'member':member, 'source':source, 'detail':author_name})
                else:
                    contact = contact_matches[0]
                    member = contact.member

                contrib, created = Contribution.objects.update_or_create(community=community, channel=channel, origin_id=origin_id, defaults={'contribution_type':self.BLOG_CONTRIBUTION, 'author':member, 'timestamp':tstamp, 'title':article_title, 'location':article_link})
                if channel.tag:
                    contrib.tags.add(channel.tag)