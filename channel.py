"""Category and video file manager — mirrors Tiny TV's folder-based channels."""
import os
import random
from config import VIDEO_ROOT, VIDEO_EXT, AUDIO_EXT, DEFAULT_SHUFFLE, DEFAULT_LOOP


class ChannelManager:
    """Scans VIDEO_ROOT for category folders and the .mjv files inside them.

    SD layout expected:
        /sd/videos/<category>/<name>.mjv
        /sd/videos/<category>/<name>.wav  (optional — synced audio)
    """

    def __init__(self):
        self.categories   = []    # list of category names (sorted)
        self._cat_idx     = 0
        self._vid_idx     = 0
        self._playlist    = []    # video basenames for current category
        self.shuffle      = DEFAULT_SHUFFLE
        self.loop         = DEFAULT_LOOP

    # ── scanning ──────────────────────────────────────────────────────────────
    def scan(self):
        """Populate categories list; returns number of categories found."""
        self.categories = []
        try:
            entries = os.listdir(VIDEO_ROOT)
        except OSError:
            return 0
        for name in sorted(entries):
            path = VIDEO_ROOT + '/' + name
            try:
                if os.stat(path)[0] & 0x4000:   # directory bit
                    # Only include if it actually contains .mjv files
                    if self._count_videos(path) > 0:
                        self.categories.append(name)
            except OSError:
                pass
        if self.categories:
            self._cat_idx = 0
            self._load_playlist()
        return len(self.categories)

    def _count_videos(self, path):
        try:
            return sum(1 for n in os.listdir(path) if n.endswith(VIDEO_EXT))
        except OSError:
            return 0

    def _load_playlist(self):
        if not self.categories:
            self._playlist = []
            return
        path  = VIDEO_ROOT + '/' + self.categories[self._cat_idx]
        names = sorted(n[:-len(VIDEO_EXT)]
                       for n in os.listdir(path) if n.endswith(VIDEO_EXT))
        if self.shuffle:
            # Fisher-Yates in-place shuffle
            for i in range(len(names) - 1, 0, -1):
                j = random.randint(0, i)
                names[i], names[j] = names[j], names[i]
        self._playlist = names
        self._vid_idx  = 0

    # ── navigation ────────────────────────────────────────────────────────────
    def next_video(self):
        """Advance to next video; wraps around within category."""
        if not self._playlist:
            return
        self._vid_idx = (self._vid_idx + 1) % len(self._playlist)
        if self._vid_idx == 0 and self.shuffle:
            self._load_playlist()   # reshuffle on wrap

    def prev_video(self):
        if not self._playlist:
            return
        self._vid_idx = (self._vid_idx - 1) % len(self._playlist)

    def next_category(self):
        if not self.categories:
            return
        self._cat_idx = (self._cat_idx + 1) % len(self.categories)
        self._load_playlist()

    def prev_category(self):
        if not self.categories:
            return
        self._cat_idx = (self._cat_idx - 1) % len(self.categories)
        self._load_playlist()

    # ── current video info ────────────────────────────────────────────────────
    @property
    def has_content(self):
        return bool(self.categories and self._playlist)

    @property
    def category_name(self):
        return self.categories[self._cat_idx] if self.categories else ''

    @property
    def video_name(self):
        return self._playlist[self._vid_idx] if self._playlist else ''

    @property
    def video_path(self):
        if not self.has_content:
            return None
        return (VIDEO_ROOT + '/' + self.category_name
                + '/' + self.video_name + VIDEO_EXT)

    @property
    def audio_path(self):
        if not self.has_content:
            return None
        p = (VIDEO_ROOT + '/' + self.category_name
             + '/' + self.video_name + AUDIO_EXT)
        try:
            os.stat(p)
            return p
        except OSError:
            return None   # audio file is optional

    @property
    def category_index(self):
        return self._cat_idx

    @property
    def video_index(self):
        return self._vid_idx

    @property
    def video_count(self):
        return len(self._playlist)

    @property
    def category_count(self):
        return len(self.categories)

    def status_line(self):
        """Short string for debug / overlay display."""
        return '{}/{} | {}'.format(
            self.category_name, self.video_name,
            '{}/{}'.format(self._vid_idx + 1, len(self._playlist))
        )
