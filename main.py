import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
import pytz

from typing import Optional

import PIL
import cv2
import ffmpeg

from PIL import Image, ImageDraw, ImageFont


def parse_video(video_path):
    try:
        probe = ffmpeg.probe(str(video_path))
    except ffmpeg.Error as e:
        print(e.stderr, file=sys.stderr)
        sys.exit(1)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream is None:
        print('No video stream found', file=sys.stderr)
    # r_frame_rate should be equivalent to avg_frame_rate for MP4 files
    # https://video.stackexchange.com/questions/20789/ffmpeg-default-output-frame-rate
    total_length_ms = int(video_stream["duration_ts"] / 100)
    return video_stream, total_length_ms


def parse_data(input_csv: str):
    with open(input_csv, newline='') as csvfile:
        config_qs = csvfile.readline()
        import urllib
        config = urllib.parse.parse_qs(config_qs)
        reader = csv.DictReader(csvfile, delimiter=";")
        ret_list = list(reader)
        timestamp = "{} {} {}".format(ret_list[0]["Date"], ret_list[0]["Time"], ret_list[0]["Millis"])
        start_time = datetime.strptime(timestamp, "%d.%m.%Y %H:%M:%S %f")
        start_time_millis = int(ret_list[0]["Millis"])
        for row in ret_list:
            row["timestamp"] = start_time + timedelta(milliseconds=(int(row["Millis"]) - start_time_millis))
        return config, ret_list


class DrawPositionManager(object):
    y_offset = 0
    x_offset = 10

    def get_pos(self):
        self.y_offset += 30
        return self.x_offset, self.y_offset


def generate_images(video_stream, data, config, camera_start_time):
    obs_data_offset = 0
    for i in range(int(video_stream["nb_frames"])):
        # Parse e.g. 30000/1001
        frames_ticks, frames_base = tuple(map(lambda x: int(x), video_stream["r_frame_rate"].split("/")))
        current_time = camera_start_time + timedelta(seconds=i * frames_base / frames_ticks)
        # TODO Handle the case where the times don't overlap
        try:
            while current_time > data[obs_data_offset]["timestamp"]:
                obs_data_offset += 1
        except IndexError:
            print("Exhausted OBS data in video frame {}".format(i))
        print("Generating frame {}".format(i))
        image = Image.new("RGBA", (video_stream["coded_width"], video_stream["coded_height"]))
        draw = ImageDraw.Draw(image)
        # TODO Either bundle font or use different font for Windows / Mac OS
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 28, encoding="unic")
        dpm = DrawPositionManager()
        draw.text(dpm.get_pos(), "This is frame {}".format(i), font=font, fill="white")
        draw.text(dpm.get_pos(), "Row in CSV: {}".format(obs_data_offset), font=font, fill="white")
        draw.text(dpm.get_pos(), "Camera time: {}".format(current_time), font=font, fill="white")
        draw.text(dpm.get_pos(), "Firmware version: {}".format(config["OBSFirmwareVersion"][0]), font=font,
                  fill="white")
        draw.text(dpm.get_pos(), "Offset Left: {}".format(config["OffsetLeft"][0]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Offset Right: {}".format(config["OffsetRight"][0]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Latitude: {}".format(data[obs_data_offset]["Latitude"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Longitude: {}".format(data[obs_data_offset]["Longitude"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "HDOP: {}".format(data[obs_data_offset]["HDOP"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Satellites: {}".format(data[obs_data_offset]["Satellites"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Left: {}".format(data[obs_data_offset]["Left"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Right: {}".format(data[obs_data_offset]["Right"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Course: {}".format(data[obs_data_offset]["Course"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Speed: {}".format(data[obs_data_offset]["Speed"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Battery Level: {}".format(data[obs_data_offset]["BatteryLevel"]), font=font,
                  fill="white")
        draw.text(dpm.get_pos(), "Confirmed: {}".format(data[obs_data_offset]["Confirmed"]), font=font, fill="white")
        draw.text(dpm.get_pos(), "Marked: {}".format(data[obs_data_offset]["Marked"]), font=font, fill="white")
        # The gauge was just a proof of concept for a nice graphical interface.
        # gauge = generate_dial(int(float(data[obs_data_offset]["Speed"]) / 60 * 180))
        # image.paste(gauge, box=(0, image.height - gauge.height))
        image.save("data/output/frame-{:010d}.png".format(i))


def generate_dial(rotation: int) -> Image:
    '''
    Generates a transparent image of a gauge with 8 ticks in 15?? intervals.
    The last sensible value is at 150??
    :param rotation: value between 0 and 150
    :return:
    '''
    output_file_name = 'new_gauge.png'

    rotation = 90 - rotation  # Factor in the needle graphic pointing to 50 (90 degrees)

    dial: Image = Image.open('needle.png')
    gauge = Image.open('gauge.png')

    radius_needle_circle = 25.0
    gauge_offset = 12
    location_top_left_needle = (int(gauge.width / 2 - gauge_offset - dial.width / 2), gauge.height - dial.height)
    location_center_of_rotation_needle = (gauge.width / 2 - gauge_offset, gauge.height - radius_needle_circle)
    background = Image.new("RGBA", (gauge.width, gauge.height), color=(0, 0, 0, 0))
    background.paste(dial, box=location_top_left_needle, mask=dial)
    background = background.rotate(rotation, resample=PIL.Image.BICUBIC,
                                   center=location_center_of_rotation_needle)  # Rotate needle

    gauge.paste(background, box=(0, int(radius_needle_circle / 2)), mask=background)  # Paste needle onto gauge
    return gauge


def autodetect_time(videofile) -> Optional[datetime]:
    """
    Tries to detect a timestamp QR code in the beginning of the video
    :param videofile:
    :return:
    """
    cap = cv2.VideoCapture(videofile)
    detector = cv2.QRCodeDetector()
    currentFrame = 0
    while currentFrame < 90:
        # TODO: OpenCV crashes on some videos with SIGSEGV. Maybe we should create a sane file with ffmpeg first and then run on that snippet instead
        # Capture frame-by-frame
        ret, frame = cap.read()
        if not ret:
            raise Exception("There was a problem reading the videofile during time detection")
        data, bbox, straight_qrcode = detector.detectAndDecode(frame)
        print(data)
        if data != "":
            return datetime.fromtimestamp(int(data) / 1000, tz=timezone.utc)
        currentFrame += 1
    return None


def offset_prompt(start_video) -> datetime:
    print("The videofile and the OBS data need to be exactly aligned.")
    print(
        "Please enter the exact time the video started (Leave empty to continue with autodetected video start: {})".format(
            start_video.strftime("%Y-%M-%D")))
    timestamp_text = input("Video Start Timestamp(YYYY-MM-DD HH:MM:SS")
    if timestamp_text == "":
        return start_video
    parsed_timestamp = datetime.strptime(timestamp_text, "%Y-%m-%d %H:%M:%S")
    localized_timestamp = parsed_timestamp.replace(tzinfo=pytz.timezone('Europe/Berlin'))
    utc_timestamp = pytz.utc.localize(localized_timestamp)
    return utc_timestamp
    # TODO parse return value


def main():
    parser = argparse.ArgumentParser(description='Overlay Open Bike Sensor data onto video files.')
    parser.add_argument('-s', '--silent', action='store_true', help="Makes script noninteractive and disables all input prompts")
    parser.add_argument('-v', '--videofile', type=str, required=True, help="Path to the videofile")
    parser.add_argument('-d', '--datafile', type=str, required=True, help="Path to the OBS CSV")
    args = parser.parse_args()
    video_stream, total_length = parse_video(args.videofile)
    config, data = parse_data(args.datafile)
    start_video: datetime = data[0]["timestamp"]
    try:
        start_video = datetime.strptime(video_stream["tags"]["creation_time"], "%Y-%m-%dT%H:%M:%S.%fZ")
    except KeyError:
        print("Timestamp could not be extract from Video Metadata")

    autodetected_start_video = autodetect_time(args.videofile)
    if autodetected_start_video is not None:
        print("Detected timestamp QR code in the video")
        start_video = autodetected_start_video
    else:
        print("No QR code detected in video")
    if not args.silent:
        start_video = offset_prompt(start_video)
    generate_images(video_stream, data, config, start_video)


if __name__ == '__main__':
    main()
