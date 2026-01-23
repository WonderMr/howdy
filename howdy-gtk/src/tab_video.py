import configparser

from i18n import _
import paths_factory

from gi.repository import Gtk as gtk
from gi.repository import Gdk as gdk
from gi.repository import GdkPixbuf as pixbuf
from gi.repository import GObject as gobject

MAX_HEIGHT = 300
MAX_WIDTH = 300


def on_page_switch(self, notebook, page, page_num):
	if page_num == 1:

		try:
			self.config = configparser.ConfigParser()
			self.config.read(paths_factory.config_file_path())
		except Exception:
			print(_("Can't open camera"))

		path = self.config.get("video", "device_path")

		try:
			# if not self.cv2:
			import cv2
			self.cv2 = cv2
		except Exception:
			print(_("Can't import OpenCV2"))

		try:
			self.capture = cv2.VideoCapture(path, cv2.CAP_V4L2)
			
			if not self.capture.isOpened():
				print(_("Can't open camera"))
				return
			
			# IMPORTANT: Set properties BEFORE reading first frame
			# Use lower resolution for preview (640x480 is enough)
			self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
			self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
			self.capture.set(cv2.CAP_PROP_FPS, 30)
			# Try MJPEG format (faster compression)
			self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
			
			# Read and discard first frame to apply settings
			self.capture.read()
			
			# Verify settings applied
			actual_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
			actual_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
			actual_fps = self.capture.get(cv2.CAP_PROP_FPS)
			print(f"Camera initialized: {actual_width}x{actual_height} @ {actual_fps} FPS")
			
		except Exception as e:
			print(f"Can't open camera: {e}")

		opencvbox = self.builder.get_object("opencvbox")
		opencvbox.modify_bg(gtk.StateType.NORMAL, gdk.Color(red=0, green=0, blue=0))

		height = self.capture.get(self.cv2.CAP_PROP_FRAME_HEIGHT) or 1
		width = self.capture.get(self.cv2.CAP_PROP_FRAME_WIDTH) or 1

		self.scaling_factor = (MAX_HEIGHT / height) or 1

		if width * self.scaling_factor > MAX_WIDTH:
			self.scaling_factor = (MAX_WIDTH / width) or 1

		config_height = self.config.getfloat("video", "max_height", fallback=320.0)
		config_scaling = (config_height / height) or 1

		self.builder.get_object("videoid").set_text(path.split("/")[-1])
		self.builder.get_object("videores").set_text(str(int(width)) + "x" + str(int(height)))
		self.builder.get_object("videoresused").set_text(str(int(width * config_scaling)) + "x" + str(int(height * config_scaling)))
		self.builder.get_object("videorecorder").set_text(self.config.get("video", "recording_plugin", fallback=_("Unknown")))

		# Initialize frame skip counter for performance
		self.video_frame_counter = 0
		self.video_processing = False
		
		# Start frame capture loop with 40ms interval (~25 FPS, smoother for UI)
		gobject.timeout_add(40, self.capture_frame)

	elif self.capture is not None:
		self.capture.release()
		self.capture = None


def capture_frame(self):
	if self.capture is None:
		return False  # Stop timer if capture is closed

	# Skip processing if previous frame is still being processed
	if getattr(self, 'video_processing', False):
		return True
	
	self.video_processing = True
	
	try:
		ret, frame = self.capture.read()
		
		# Check if frame was read successfully
		if not ret or frame is None or frame.size == 0:
			self.video_processing = False
			return True  # Continue trying

		# Resize frame (use INTER_NEAREST for fastest performance on preview)
		frame = self.cv2.resize(frame, None, fx=self.scaling_factor, fy=self.scaling_factor, interpolation=self.cv2.INTER_NEAREST)
		
		# Convert BGR to RGB (OpenCV uses BGR by default)
		frame = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
		
		# Get frame dimensions
		height, width, channels = frame.shape
		
		# Create Pixbuf directly from frame data
		# CRITICAL: Keep frame reference alive until pixbuf is used!
		# Store frame as instance variable to prevent garbage collection
		self._current_frame_data = frame.copy()
		pixbuf_data = self._current_frame_data.tobytes()
		
		pb = pixbuf.Pixbuf.new_from_data(
			pixbuf_data,
			pixbuf.Colorspace.RGB,
			False,  # no alpha channel
			8,      # bits per sample
			width,
			height,
			width * channels  # rowstride
		)

		self.opencvimage.set_from_pixbuf(pb)
	
	except Exception as e:
		print(f"ERROR in capture_frame: {e}")
		import traceback
		traceback.print_exc()
	finally:
		self.video_processing = False

	return True  # Continue capturing
