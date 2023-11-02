import json
import time

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    bool_or_none,
    float_or_none,
    int_or_none,
    join_nonempty,
    js_to_json,
    try_call,
    unified_strdate,
    url_or_none,
)
from yt_dlp.utils.traversal import traverse_obj


class NetflixTrailerIE(InfoExtractor):
    IE_NAME = 'NetflixTrailer'
    IE_DESC = 'DRM-free trailers and teasers from Netflix'
    _VALID_URL = r'https?://(?:www\.)?netflix\.com/(?:[a-zA-Z_-]*/)?title/\d+\?(?:[^#]+&)?clip=(?P<id>\d+)'
    _TESTS = [{
        'url': 'https://www.netflix.com/title/81040344?clip=81499051',
        'md5': '9032282465b38f310765345edabc7f78',
        'info_dict': {
            'id': '81499051',
            'ext': 'mp4',
            'title': 'Season 1 Trailer 2: Squid Game',
            'description': '',
            'thumbnail': r're:^https?://.*nflxso\.net.*\.jpg',
            'duration': 91,
        },
    }, {
        'url': 'https://www.netflix.com/title/81435227?s=i&trkid=13747225&clip=81441302&t=twt',
        'md5': '29d19cb6e1d44e13d80c762e76d6f942',
        'info_dict': {
            'id': '81441302',
            'ext': 'mp4',
            'title': 'Trailer: Fatherhood',
            'description': 'md5:98237a071ad2171851b9269c5d2e6511',
            'thumbnail': r're:^https?://.*nflxso\.net.*\.jpg',
            'duration': 152,
        },
    }, {
        'url': 'https://www.netflix.com/title/81587446?clip=81659792',
        'md5': '3a60bf3363abb6e6e1ecacf35eb1a33b',
        'info_dict': {
            'id': '81659792',
            'ext': 'mp4',
            'title': 'Season 1 Trailer: Physical: 100',
            'description': 'md5:7dea7d37bea80805025639f6a1291224',
            'thumbnail': r're:^https?://.*nflxso\.net.*\.jpg',
            'duration': 183,
        },
        'expected_warnings': ['Error in manifest request for codec av1'],
    }]

    VIDEO_PROFILES = {
        'vp9': [
            'vp9-profile0-L21-dash-cenc',
            'vp9-profile0-L30-dash-cenc',
            'vp9-profile0-L31-dash-cenc',
            'vp9-profile0-L40-dash-cenc',
        ],
        'avc-main': [
            'playready-h264mpl30-dash',
            'playready-h264mpl31-dash',
            'playready-h264mpl40-dash',
        ],
        'avc-high': [
            'playready-h264hpl22-dash',
            'playready-h264hpl30-dash',
            'playready-h264hpl31-dash',
            'playready-h264hpl40-dash',
        ],
        'av1': [
            'av1-main-L20-dash-cbcs-prk',
            'av1-main-L21-dash-cbcs-prk',
            'av1-main-L30-dash-cbcs-prk',
            'av1-main-L31-dash-cbcs-prk',
            'av1-main-L40-dash-cbcs-prk',
            'av1-main-L41-dash-cbcs-prk',
            'av1-main-L50-dash-cbcs-prk',
            'av1-main-L51-dash-cbcs-prk',
        ],
    }

    AUDIO_PROFILES = {
        'eac3': [
            'ddplus-2.0-dash',
            'ddplus-5.1-dash',
            'ddplus-5.1hq-dash',
            'ddplus-atmos-dash',
        ],
        'aac': [
            'heaac-2-dash',
            'heaac-5.1-dash',
            'heaac-2hq-dash',
        ],
        'usac': [
            'xheaac-dash',
        ],
    }

    # Sorted lowest to highest priority
    SUBTITLE_EXT = {
        'nflx-cmisc': 'cmisc',
        'simplesdh': 'simplesdh',
        'imsc1.1': 'imcs1',
        'dfxp-ls-sdh': 'dfxp',
        'webvtt-lssdh-ios8': 'vtt',
    }

    def request_manifest(self, react_json, clip_id, vcodec, acodec, partial=False):
        profiles = self.VIDEO_PROFILES.get(vcodec, []) + self.AUDIO_PROFILES.get(acodec, [])
        query = {
            'reqAttempt': '1',
            'reqName': 'manifest',
            **traverse_obj(react_json, ('models', 'abContext', 'data', 'headers', {
                'clienttype': 'X-Netflix.clientType',
                'uiversion': 'X-Netflix.uiVersion',
                'browsername': 'X-Netflix.browserName',
                'browserversion': 'X-Netflix.browserVersion',
                'osname': 'X-Netflix.osName',
                'osversion': 'X-Netflix.osVersion',
            })),
        }
        data = {
            'version': 2,
            'url': 'manifest',
            'id': int(time.time() * 10 ** 8),
            'params': {
                'type': 'standard',
                'manifestVersion': 'v2',
                'viewableId': str(clip_id),
                'profiles': [
                    *profiles,
                    *self.SUBTITLE_EXT.keys(),
                ],
                'flavor': 'SUPPLEMENTAL',
                'drmType': 'widevine',
                'drmVersion': 25,
                'usePsshBox': True,
                'isBranching': False,
                'useHttpsStreams': True,
                'supportsUnequalizedDownloadables': True,
                'imageSubtitleHeight': 1080,
                **traverse_obj(react_json, ('models', 'playerModel', 'data', 'config', {
                    'uiVersion': ('ui', 'initParams', 'uiVersion'),
                    'uiPlatform': ('ui', 'initParams', 'uiPlatform'),
                    'clientVersion': ('core', 'assets', 'version'),
                    'platform': ('core', 'initParams', 'browserInfo', 'version'),
                    'osVersion': ('core', 'initParams', 'browserInfo', 'os', 'version'),
                    'osName': ('core', 'initParams', 'browserInfo', 'os', 'name'),
                })),
                'supportsPreReleasePin': True,
                'supportsWatermark': True,
                'videoOutputInfo': [
                    {
                        'type': 'DigitalVideoOutputDescriptor',
                        'outputType': 'unknown',
                        'supportedHdcpVersions': [],
                        'isHdcpEngaged': False,
                    }
                ],
                'titleSpecificData': {str(clip_id): {'unletterboxed': True}},
                'preferAssistiveAudio': False,
                'isUIAutoPlay': False,
                'isNonMember': True,
                'desiredVmaf': 'plus_lts',
                'desiredSegmentVmaf': 'plus_lts',
                'requestSegmentVmaf': False,
                'supportsPartialHydration': partial,
                'contentPlaygraph': ['start'],
                'supportsAdBreakHydration': True,
                'liveMetadataFormat': 'INDEXED_SEGMENT_TEMPLATE',
                'useBetterTextUrls': True,
                'showAllSubDubTracks': not partial,
            },
        }

        return self._download_json(
            'https://www.netflix.com/playapi/cadmium/manifest/1', clip_id, query=query,
            data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'text/plain'},
            note=f'Downloading {vcodec}/{acodec} manifest',
        )

    def extract_audiotracks(self, acodec, manifest):
        formats = []
        for audio_track in traverse_obj(manifest, ('result', 'audio_tracks'), default=[]):
            for stream in audio_track.get('streams', []):
                formats.append({
                    'format_id': join_nonempty('content_profile', 'language', 'bitrate', from_dict=stream, delim='-'),
                    'format_note': join_nonempty('languageDescription', 'surroundFormatLabel', from_dict=audio_track, delim='-'),
                    'ext': 'mp4',
                    'vcodec': 'none',
                    'acodec': acodec,
                    **traverse_obj(stream, {
                        'url': ('urls', 0, 'url', {url_or_none}),
                        'abr': ('bitrate', {int_or_none}),
                        'filesize': ('size', {int_or_none}),
                        'has_drm': ('isDrm', {bool_or_none}),
                    }),
                    'audio_channels': try_call(lambda: sum([int(x) for x in stream.get('channels').split('.')])),
                    'language': audio_track.get('language'),
                    'preference': 1 if audio_track.get('isNative') else -1,
                })
        return formats

    def _real_extract(self, url):
        clip_id = self._match_id(url)
        webpage = self._download_webpage(url, clip_id)
        react_json = self._search_json(
            r'netflix\.reactContext\s*=\s*', webpage, 'react context',
            clip_id, transform_source=js_to_json)

        formats = []
        subtitles = {}

        first = True
        for vcodec in self.VIDEO_PROFILES.keys():
            first_acodec = list(self.AUDIO_PROFILES.keys())[0]
            manifest = self.request_manifest(react_json, clip_id, vcodec, first_acodec, partial=not first)
            if 'error' in manifest:
                self.report_warning(f'Error in manifest request for codec {vcodec}/{first_acodec}')
                continue
            for video_track in traverse_obj(manifest, ('result', 'video_tracks'), default=[]):
                for stream in video_track.get('streams', []):
                    formats.append({
                        'format_id': join_nonempty('content_profile', 'bitrate', from_dict=stream, delim='-'),
                        'ext': 'mp4',
                        'vcodec': vcodec,
                        'acodec': 'none',
                        **traverse_obj(stream, {
                            'url': ('urls', 0, 'url', {url_or_none}),
                            'width': ('res_w', {int_or_none}),
                            'height': ('res_h', {int_or_none}),
                            'vbr': ('bitrate', {int_or_none}),
                            'filesize': ('size', {int_or_none}),
                            'has_drm': ('isDrm', {bool_or_none}),
                        }),
                        'fps': float_or_none(stream.get('framerate_value'), stream.get('framerate_scale')),
                    })

            if not first:
                continue
            first = False

            formats.extend(self.extract_audiotracks(first_acodec, manifest))
            for acodec in list(self.AUDIO_PROFILES.keys())[1:]:
                audio_manifest = self.request_manifest(react_json, clip_id, vcodec, acodec)
                if 'error' in manifest:
                    self.report_warning(f'Error in manifest request for codec {vcodec}/{acodec}')
                    continue
                formats.extend(self.extract_audiotracks(acodec, audio_manifest))

            for subtitle_track in traverse_obj(manifest, ('result', 'timedtexttracks'), default=[]):
                if subtitle_track.get('isNoneTrack'):
                    continue
                lang = subtitle_track.get('language')
                if subtitle_track.get('rawTrackType') == 'closedcaptions':
                    lang += '_cc'
                if subtitle_track.get('isForcedNarrative'):
                    lang += '_forced'
                if lang in subtitles:
                    self.report_warning(f'Duplicate subtitle track {lang}')
                    continue
                subtitles[lang] = []

                downloadables = subtitle_track.get('ttDownloadables', {})
                downloadables = {k: downloadables[k] for k in self.SUBTITLE_EXT.keys() if k in downloadables}
                for format, data in downloadables.items():
                    name = subtitle_track.get('languageDescription')
                    if subtitle_track.get('rawTrackType') == 'closedcaptions':
                        name += ' - CC'
                    if subtitle_track.get('isForcedNarrative'):
                        name = f'Forced Narrative ({subtitle_track.get("language")})'
                    subtitles[lang].append({
                        'ext': self.SUBTITLE_EXT.get(format),
                        'url': traverse_obj(data, ('urls', 0, 'url', {url_or_none})),
                        'name': name,
                    })

        return {
            'id': clip_id,
            **traverse_obj(react_json, (
                'models', 'nmTitleUI', 'data', 'sectionData',
                lambda _, v: v['type'] == 'additionalVideos', 'data', 'supplementalVideos',
                lambda _, v: v['id'] == int(clip_id), {
                    'title': 'title',
                    'description': 'synopsis',
                    'duration': ('runtime', {int_or_none}),
                    'thumbnail': ('placeholderImageUrl', {url_or_none}),
                }), get_all=False),
            'formats': formats,
            'subtitles': subtitles,
        }


class NetflixTrailerPageIE(InfoExtractor):
    IE_NAME = 'NetflixTrailer:page'
    IE_DESC = 'DRM-free trailers and teasers from Netflix\'s show/movie pages'
    _VALID_URL = r'https?://(?:www\.)?netflix\.com/(?:[a-zA-Z_-]*/)?title/(?P<id>\d+)$'
    _TESTS = [{
        'url': 'https://www.netflix.com/title/81435227',
        'info_dict': {
            'id': '81435227',
            'title': 'Fatherhood',
            'release_date': '20210101',
            'description': 'md5:80610df33173bb555f145b47358217c9',
            'age_limit': 6,
            'cast': ['Kevin Hart', 'Alfre Woodard', 'Lil Rel Howery'],
        },
        'playlist_count': 1,
    }, {
        'url': 'https://www.netflix.com/us/title/81040344',
        'info_dict': {
            'id': '81040344',
            'title': 'Squid Game',
            'release_date': '20210101',
            'description': 'md5:730219e5007ed51caf1048632582b68c',
            'age_limit': 16,
            'cast': ['Lee Jung-jae', 'Park Hae-soo', 'Wi Ha-jun'],
        },
        'playlist_count': 4,
    }, {
        'url': 'https://www.netflix.com/de-en/title/70142405',
        'info_dict': {
            'id': '70142405',
            'title': 'Avatar: The Last Airbender',
            'release_date': '20050101',
            'description': 'md5:513bac1f38adf46b1d95cbf7e9aae8bb',
            'age_limit': 6,
            'cast': ['Zach Tyler', 'Mae Whitman', 'Jack De Sena'],
        },
        'playlist_count': 0,
    }]

    def _real_extract(self, url):
        content_id = self._match_id(url)
        webpage = self._download_webpage(url, content_id)
        react_json = self._search_json(
            r'netflix\.reactContext\s*=\s*', webpage, 'react context',
            content_id, transform_source=js_to_json)

        section_data = traverse_obj(react_json, ('models', 'nmTitleUI', 'data', 'sectionData'))

        return {
            '_type': 'playlist',
            'id': content_id,
            'entries': [
                self.url_result(f'https://www.netflix.com/title/{content_id}?clip={vid["id"]}',
                                NetflixTrailerIE, vid['id'], vid.get('title'))
                for vid in traverse_obj(section_data, (
                    lambda _, v: v['type'] == 'additionalVideos', 'data', 'supplementalVideos', ...))
            ],
            **traverse_obj(section_data, (lambda _, v: v['type'] == 'hero', 'data', 'details',
                                          lambda _, v: v['type'] == 'titleMetadata', 'data', {
                'title': 'title',
                'description': 'synopsis',
                'release_date': ('year', {lambda y: f'{y}0101'}, {unified_strdate}),
                'cast': 'starring',
                'age_limit': ('maturityDetails', 'value', {int_or_none}),
            }), get_all=False),
        }
