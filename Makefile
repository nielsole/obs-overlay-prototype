
generate-frames:
	python ./main.py -s -v $VIDEO_FILE -d $DATA_FILE
	touch generate-frames

overlay-video: generate-frames
	ffmpeg -i $VIDEO_FILE  -pattern_type glob -i 'data/output/*.png' -filter_complex "[0:0][1:0]overlay[out]" -shortest -map [out] -map 0:1 -pix_fmt yuv420p -c:a copy -c:v libx264 -crf 18  data/output/output.mov
	touch overlay-video
