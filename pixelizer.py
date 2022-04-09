import numpy as np
import mimetypes
import argparse
import ffmpeg
import time
import cv2
import os
import matplotlib.pyplot as plt


class Pixelizer:
	'''
	Pixelizer is a specialized class for anonymizing images/videos.
	'''

	def __init__(self, directory):
		prototxtPath = os.path.sep.join([directory, "deploy.prototxt.txt"])
		weightsPath = os.path.sep.join([directory, "res10_300x300_ssd_iter_140000.caffemodel"])
		self.net = cv2.dnn.readNet(prototxtPath, weightsPath)


	def pixelizer(self, img, blocks=10):
		(h, w) = img.shape[:2]
		xSteps = np.linspace(0, w, blocks + 1, dtype="int")
		ySteps = np.linspace(0, h, blocks + 1, dtype="int")
		for i in range(1, len(ySteps)):
			for j in range(1, len(xSteps)):
				startX = xSteps[j - 1]
				startY = ySteps[i - 1]
				endX = xSteps[j]
				endY = ySteps[i]
				roi = img[startY:endY, startX:endX]
				(B, G, R) = [int(x) for x in cv2.mean(roi)[:3]]
				cv2.rectangle(img, (startX, startY), (endX, endY),
					(B, G, R), -1)
		return img


	def preprocessing(self, img):
		(h, w) = img.shape[0], img.shape[1]
		blob = cv2.dnn.blobFromImage(img, 1.0, (300, 300),
			(104.0, 177.0, 123.0))
		self.net.setInput(blob)
		detections = self.net.forward()
		for i in range(0, detections.shape[2]):
			confidence = detections[0, 0, i, 2]
			if confidence > 0.3:
				box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
				(startX, startY, endX, endY) = box.astype("int")
				face = img[startY:endY, startX:endX]
				face = self.pixelizer(face, blocks=10)
				img[startY:endY, startX:endX] = face
		return img


	def extract(self, input_path, output_path):
		probe = ffmpeg.probe(input_path)
		codec_name_audio = probe['streams'][1]['codec_name']
		codec_name_video = probe['format']['filename'].split('.')[-1]
		self.audio_file = '.'.join(["audio", codec_name_audio])
		self.video_file = '.'.join(["video", codec_name_video])
		self.pre_result = '.'.join(["pre_result", codec_name_video])
		self.output = output_path
		os.system(f"ffmpeg -i {input} -map 0:a {self.audio_file} -map 0:v {self.video_file}")
		self.info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
		self.width = int(self.info['width'])
		self.height = int(self.info['height'])
		out, _ = (
			ffmpeg
			.input(self.video_file)
			.output('pipe:', format='rawvideo', pix_fmt='rgb24')
			.run(capture_stdout=True)
		)
		video = (
			np
			.frombuffer(out, np.uint8)
			.reshape([-1, self.height, self.width, 3])
		)
		input_array = video.copy()
		del video
		return input_array


	def frames_to_video(self, array):
		fps = cv2.VideoCapture(self.video_file).get(cv2.CAP_PROP_FPS)
		if self.info.get('color_space', False) != False:
			colorspace = self.info['color_space']
		else:
			colorspace = 'bt709'
		process2 = (
			ffmpeg
			.input('pipe:', format='rawvideo', pix_fmt='rgb24', s='{}x{}'.format(self.width, self.height), framerate=fps, colorspace=colorspace)
			.output(self.pre_result, pix_fmt=self.info['pix_fmt'])
			.overwrite_output()
			.run_async(pipe_stdin=True))
		for img in array:
			process2.stdin.write(
				img
				.astype(np.uint8)
				.tobytes()
				)
		process2.stdin.close()
		time.sleep(10)
		os.system(f"ffmpeg -i {self.pre_result} -i {self.audio_file} -shortest {self.output}")
		pixelizer.delete_tmp()

	def delete_tmp(self):
		os.remove(self.pre_result)
		os.remove(self.audio_file)
		os.remove(self.video_file)


	def input(self, array):
		for i, img in enumerate(array):
			array[i] = self.preprocessing(img)


def get_args():
	ap = argparse.ArgumentParser()
	ap.add_argument("input")
	ap.add_argument("output")
	res = ap.parse_args()
	return res.input, res.output


if __name__ == '__main__':
	input, output = get_args()
	file_type = mimetypes.guess_type(input)[0].split('/')[0]
	pixelizer = Pixelizer("source")
	if file_type == 'video':
		array = pixelizer.extract(input, output)
	else:
		array = np.expand_dims(cv2.imread(input), axis = 0)
	pixelizer.input(array)
	if file_type == 'video':
		pixelizer.frames_to_video(array)
	else:
		cv2.imwrite(output, np.squeeze(array, axis=0))
