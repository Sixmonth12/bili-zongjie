import unittest
from unittest.mock import patch
import server
import video_extract as video


class VideoTests(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(video.canonical_url('https://www.bilibili.com/video/BV1sK41127iZ/?p=2&tracking=x'), 'https://www.bilibili.com/video/BV1sK41127iZ/?p=2')
        for value in ('http://127.0.0.1/', 'https://evil.example/video/BV1sK41127iZ/', 'https://www.bilibili.com/video/BV1sK41127iZ/?p=-1'):
            with self.assertRaises(ValueError): video.canonical_url(value)

    def test_subtitle_short_circuit(self):
        with patch.object(server, 'import_bilibili', return_value={'segments': [], 'title': 'test'}):
            self.assertEqual(video.extract(server, 'BV1sK41127iZ')['source'], 'subtitle')

    def test_missing_job(self):
        with self.assertRaises(server.AppError): video.get_job(server, 'nonexistent')


if __name__ == '__main__': unittest.main()
