#
# Parse all multicast URL's from the IPTV stream list
# (Python 3!)
#
import argparse
import json
import collections
import re
import urllib

import requests

Channel = collections.namedtuple('Channel', ['name', 'url', 'extras'])


class ParseVLC(object):
    line_regex = re.compile("#EXT(?P<tag>\w+):(?P<value>.*)")

    def __init__(self, file_handle):
        self.file = file_handle

    def __iter__(self):
        ext_m3u = False

        buffer = []

        # all lines, with whitespace stripped, and blank lines filtered
        for line in filter(bool, [line.strip() for line in self.file]):
            # eat everything until a non-header line was found
            if not ext_m3u:
                if 'EXTM3U' in line:
                    ext_m3u = True
                continue

            buffer.append(line)

            # is it not a option? -> it is the address
            if not self.line_regex.match(line):
                yield self.parse_section(buffer)
                buffer = []

    def parse_section(self, section):
        name = None
        url = None
        extras = {}

        for line in section:
            m = self.line_regex.match(line)


            if m:
                tag, value = m.groups()
                if tag == 'INF':
                    _, name = value.split(',')
                if tag == 'VLCOPT':
                    key, val = value.split('=')
                    extras[key] = val
            else:
                url = line

        return Channel(name, url, extras)


"""
Wrapper for a Tvheadend instance
"""


class TvheadendAPI(object):
    def __init__(self, root, user=None, pw=None, interface='eth0'):
        self.root_url = root
        self.interface = interface
        self.auth = (user, pw) if user else None

    def post(self, sub_url, data):
        url = urllib.parse.urljoin(self.root_url, sub_url)

        res = requests.post(url,  data=data, auth=self.auth)
        return res.json()

    def get(self, sub_url, params):
        url = urllib.parse.urljoin(self.root_url, sub_url)

        res = requests.get(url,  params=params, auth=self.auth)
        return res.json()

    """
    Add IPTV channel to the first Tvheadend mux
    with the first index. Make sure that max input streams
    attribute of the Network is set low enough (!)

    channel: Channel namedtuple for given channel
    """
    def add_mux(self, channel):
        # Get the UUID of the iptv network by assuming it is the first
        uuid_request = self.post("/api/idnode/load", data={
            'class': "mpegts_network",
            'enum': 1,
            'query': ''
        })

        if not uuid_request['entries']:
            print("""Make sure that there exists a network in tvheadend.

            It should be of IPTV type and the number of maximum input
            streams should be low.

            Tvheadend will try to subscribe to all the channels that get
            added. If this number is too high, it could cause your tvheadend
            instance to stop responding.
            """)

        network_uuid = uuid_request['entries'][0]['key']

        self.post("/api/mpegts/network/mux_create", data={
            'uuid': network_uuid,
            'conf': json.dumps({
                "enabled": 1,
                "skipinitscan": 1,
                "iptv_muxname": channel.name,
                "iptv_sname": channel.name,
                "iptv_url": channel.url,
                "iptv_interface": self.interface,
                "charset": "AUTO"
            })
        })

    def list_muxes(self):
        res = self.post("/api/mpegts/mux/grid", data={
            'start': 0,
            'limit': 999999999,
            'sort': 'name',
            'dir': 'ASC',
        })

        for mux in res['entries']:
            yield Channel(mux['name'], mux['iptv_url'], mux)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Bulk-add channels to Tvheadend, from a M3U file')
    parser.add_argument('m3u_file', type=argparse.FileType('r'))
    parser.add_argument('tvheadend_url',
                        help='URL to tvheadend, e.g. http://192.168.1.2:9981')
    parser.add_argument('--user', default=None, help="username")
    parser.add_argument('--password', default=None, help="password")
    parser.add_argument('--interface', default='eth0',
                        help='interface name TVHeadend tunes on (e.g. eth0)')

    args = parser.parse_args()

    m3u_parser = ParseVLC(args.m3u_file)
    tvh = TvheadendAPI(args.tvheadend_url, args.user, args.password,
                       args.interface)

    # Create a dict of the URL's of known channels:
    known_channels = {m.url: m for m in tvh.list_muxes()}

    for channel in m3u_parser:
        if channel.url not in known_channels:
            print('added: {} at {}'.format(channel.name, channel.url))
            tvh.add_mux(channel)
        else:
            print('skipped: {} at {}'.format(channel.name, channel.url))
