from contextlib import closing
import subprocess
from audiotsm import phasevocoder
from audiotsm.io.wav import WavReader, WavWriter
from scipy.io import wavfile
import numpy as np
import re
import math
from shutil import copyfile, rmtree
import os
import argparse
import cv2
from tqdm import tqdm
from time import sleep
# from pytube import YouTube


# def downloadFile(url):
#     name = YouTube(url).streams.first().download()
#     newname = name.replace(' ', '_')
#     os.rename(name, newname)
#     return newname


def getMaxVolume(s):
    maxv = float(np.max(s))
    minv = float(np.min(s))
    return max(maxv, -minv)


def createPath(s):
    #assert (not os.path.exists(s)), "The filepath "+s+" already exists. Don't want to overwrite it. Aborting."

    try:
        os.mkdir(s)
    # except:
    #     os.rmdir(s)
    #     os.mkdir(s)
    #     print("had error with temp folder")
    except OSError:
        assert False, "Creation of the directory %s failed. (The TEMP folder may already exist. Delete or rename it, and try again.)"


def inputToOutputFilename(filename):
    dotIndex = filename.rfind(".")
    return filename[:dotIndex]+"_ALTERED"+filename[dotIndex:]


def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return float(result.stdout)

parser = argparse.ArgumentParser(description='Modifies a video file to play at different speeds when there is sound vs. silence.')
parser.add_argument('-i','--input_file', type=str,  help='the video file you want modified')
# parser.add_argument('--url', type=str, help='A youtube url to download and process')
parser.add_argument('-o','--output_file', type=str, default="", help="the output file. (optional. if not included, it'll just modify the input file name)\nIf use -m then write the extension instead")
parser.add_argument("-st",'--silent_threshold', type=float, default=0.03, help="the volume amount that frames' audio needs to surpass to be consider \"sounded\". It ranges from 0 (silence) to 1 (max volume)")
parser.add_argument('-fm','--frame_margin', type=float, default=3, help="some silent frames adjacent to sounded frames are included to provide context. How many frames on either the side of speech should be included? That's this variable.")
parser.add_argument('-s','--small', type=bool, default=False,  help='This can aliviate the amount of storaged used, however may increase run time')
parser.add_argument('-m','--multiple_files', type=str, default="",  help='Put the directory where they will be outputed. DO NOT INCLUDE THE DOT. Also if -o is not used then it will be a .mp4 file.')
parser.add_argument('-cl','--command_length', type=int, default=100,  help='This changes the length per command of each file or changes the amount of clips per video. The smaller the value the better you will be able to know how log it will take to complete, but will take longer. The maximumn value set is 120.')


args = parser.parse_args()

FILE_NAME = args.input_file
# if args.url != None:
#     FILE_NAME = downloadFile(args.url)
# else:
#     FILE_NAME = args.input_file


SILENT_THRESHOLD = args.silent_threshold

FRAME_SPREADAGE = args.frame_margin

MULTIPLE_FILES = args.multiple_files
if(MULTIPLE_FILES):
    print("File Name:")
    print(FILE_NAME)

TEMP_FOLDER = "temp"

if(len(MULTIPLE_FILES)>= 1):
    if len(args.output_file) >= 1:
        OUTPUT_FILE = args.output_file
    else:
        OUTPUT_FILE = "mp4"
    index_1 = FILE_NAME.rfind(".")
    index_2 = FILE_NAME.rfind("/") + 1
    fileName = FILE_NAME[:index_1][index_2:]
    OUTPUT_FILE = "{}/{}.{}".format(MULTIPLE_FILES,fileName,OUTPUT_FILE.lower())
else:
    if len(args.output_file) >= 1:
        OUTPUT_FILE = args.output_file
    else:
        OUTPUT_FILE = inputToOutputFilename(FILE_NAME)

print("Output File: {}".format(OUTPUT_FILE))



LENGTH_PER_COMMAND = args.command_length

#changing this value could cause there to be an error
MAX = 120
if LENGTH_PER_COMMAND>MAX:
    LENGTH_PER_COMMAND = MAX

createPath(TEMP_FOLDER)

print("Creating Audio File")
try:
    command = "ffmpeg -hide_banner -loglevel panic -i {} {}/audio.wav".format(FILE_NAME, TEMP_FOLDER)
    subprocess.Popen(command, shell=True).wait()
except:
    command = "rm -r " + TEMP_FOLDER
    subprocess.run(command,shell=True)
    print("Problem with file name: {}".format(FILE_NAME))

cap = cv2.VideoCapture(FILE_NAME)
fps = cap.get(cv2.CAP_PROP_FPS)

print("Getting Audio from Video")
sampleRate, audioData = wavfile.read("{}/audio.wav".format(TEMP_FOLDER))
audioSampleCount = audioData.shape[0]
maxAudioVolume = getMaxVolume(audioData)

samplesPerFrame = sampleRate/fps

audioFrameCount = int(math.ceil(audioSampleCount/samplesPerFrame))

hasLoudAudio = np.zeros((audioFrameCount))

print("Analyzing Audio")
for i in range(audioFrameCount):
    start = int(i*samplesPerFrame)
    end = min(int((i+1)*samplesPerFrame), audioSampleCount)
    audiochunks = audioData[start:end]
    maxchunksVolume = float(getMaxVolume(audiochunks))/maxAudioVolume
    if maxchunksVolume >= SILENT_THRESHOLD:
        hasLoudAudio[i] = 1
timing = [[0,1/fps,hasLoudAudio[0]]]

# if(get_length(FILE_NAME) != audioSampleCount/sampleRate):
#         print("don't match")

for i in range(1,len(hasLoudAudio)):
    sound = 0
    if(hasLoudAudio[i]):
        sound = 1
    if(timing[len(timing)-1][2] == sound):
        timing[len(timing)-1][1] += 1/fps
    else:
        timing.append([i/fps, (i+1)/fps, sound])
i=0
while i < len(timing):
    if(timing[i][2] == 0):
        del timing[i]
        continue
    i+=1

# print(len(timing))
i=0
while i < len(timing):
    if(timing[i][2]):
        if(timing[i][0] >= timing[i][1]):
            del timing[i]
            continue
        timing[i][0] -= FRAME_SPREADAGE/fps
        if(timing[i][0]<0):
            timing[i][0] = 0
        timing[i][1] += FRAME_SPREADAGE/fps
        if(timing[i][1] > audioSampleCount/sampleRate):
            timing[i][1] = audioSampleCount/sampleRate
    i+=1
i=1
while i < len(timing):
    if(timing[i-1][1] >= timing[i][0]):
        timing[i-1][1] = timing[i][1]
        del timing[i]
        continue
    i+=1

i=0
while i < len(timing):
    if(timing[i][0]<0):
        timing[i][0] = 0
        if(timing[i][1]<0):
            del timing[i]
            continue
    if(timing[i][1] > audioSampleCount/sampleRate):
        if(timing[i][0] > audioSampleCount/sampleRate):
            del timing[i]
            continue
        else:
            timing[i][1] = audioSampleCount/sampleRate
    i+=1
# print(timing)
if(len(timing) <= LENGTH_PER_COMMAND):
    DIR = FILE_NAME
else:
    if(args.small):
        DIR = FILE_NAME
    else:
        DIR = "{}/vid.mp4".format(TEMP_FOLDER)
        print("Creates Temperary Video")
        subprocess.Popen("ffmpeg -hide_banner -loglevel panic -i {} {}".format(FILE_NAME, DIR), shell=True).wait()
command = open("{}/temp.txt".format(TEMP_FOLDER), "w+")
command.write('ffmpeg -hide_banner -loglevel panic -i {} -filter_complex "'.format(DIR))
for i in tqdm(range(len(timing)), desc="Creating Command"):
    command.write('[0:v]trim=start={}:end={},setpts=PTS-STARTPTS[v{}]; '.format(timing[i][0], timing[i][1], i%LENGTH_PER_COMMAND))
    command.write('[0:a]atrim=start={}:end={},asetpts=PTS-STARTPTS[a{}]; '.format(timing[i][0], timing[i][1], i%LENGTH_PER_COMMAND))
    if(i % LENGTH_PER_COMMAND == LENGTH_PER_COMMAND-1):
        for m in range(LENGTH_PER_COMMAND):
            command.write('[v{}][a{}]'.format(m,m))
        command.write('concat=n={}:v=1:a=1[e][f]" -map \'[e]\' -map \'[f]\'  -strict -2 {}/{}.mp4;\n'.format(i%LENGTH_PER_COMMAND + 1, TEMP_FOLDER, math.ceil(i/(LENGTH_PER_COMMAND))))
        if(i != len(timing)):
            command.write('ffmpeg -hide_banner -loglevel panic -i {} -filter_complex "'.format(DIR))

for i in tqdm(range(len(timing) % LENGTH_PER_COMMAND), desc="Finishing Command"):
    command.write('[v{}][a{}]'.format(i,i))
if len(timing)%100 != 0:
    command.write('concat=n={}:v=1:a=1[e][f]" -map \'[e]\' -map \'[f]\' {}/final.mp4;'.format((len(timing))%LENGTH_PER_COMMAND,TEMP_FOLDER))
command.close()
command = open("{}/temp.txt".format(TEMP_FOLDER), "r")
print("Now Running Command\nRemoving Quiet Parts\nThis Process can take long")
commandList = command.read().split("\n")
command.close()
for i in tqdm(commandList):
    subprocess.Popen(i, shell=True).wait()


sleep(1)
print("Gathering Files")
file = open("{}/list.txt".format(TEMP_FOLDER), "w+")
if(math.ceil(len(timing)/LENGTH_PER_COMMAND) != 1):
    for i in range(1,math.ceil(len(timing)/LENGTH_PER_COMMAND)):
        file.write("file '{}.mp4'\n".format(i))
if len(timing)%100 != 0:
    file.write("file 'final.mp4'")
file.close()


print("Combining Parts together")
subprocess.Popen("ffmpeg -f concat -safe 0 -i {}/list.txt -c copy {}".format(TEMP_FOLDER,OUTPUT_FILE), shell=True).wait()


command = "rm -r " + TEMP_FOLDER
subprocess.run(command,shell=True)

command = "mv {} temp_vids".format(FILE_NAME)
# subprocess.run(command,shell=True)
