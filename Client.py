from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket
import threading
import sys
import traceback
import os
import time
from VideoStream import VideoStream
from RtpPacket import RtpPacket
from datetime import timedelta
import fnmatch


from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
SESSION_FILE = "session.txt"


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3

    DESCRIBE = 4

    FASTFORWARD = 5
    BACKWARD = 6
    totalTime = 0

    NEXT = 7
    BACK = 8

    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, fileName):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = fileName
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0

        # Adding
        self.bytesReceived = 0
        self.startTime = 0
        self.lossCounter = 0

        # change video
        self.curVideo = 0
        # check cache
        self.cache = False

    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        self.setup = Button(self.master, width=15, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=2, column=0, padx=2, pady=2)
        self.setup["state"] = "normal"

        # Create Play button
        self.start = Button(self.master, width=15, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=3, column=1, padx=2, pady=2)
        self.start["state"] = "disabled"

        # Create Pause button
        self.pause = Button(self.master, width=15, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=3, column=2, padx=2, pady=2)
        self.pause["state"] = "disabled"

        # Create Teardown button
        self.teardown = Button(self.master, width=15, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=2, column=3, padx=2, pady=2)
        self.teardown["state"] = "disabled"

        # Create a label to display the movie
        self.label = Label(self.master, height=18, bg="black")
        self.label.grid(row=0, column=0, columnspan=4,
                        sticky=W+E+N+S, padx=5, pady=5)

        # Create a label to display the time
        self.timeBox = Label(self.master, width=12, text="00:00")
        self.timeBox.grid(row=1, column=1, columnspan=2,
                          sticky=W+E+N+S, padx=5, pady=5)

        # Create Describe button
        self.describe = Button(self.master, width=15, padx=3, pady=3)
        self.describe["text"] = "Describe"
        self.describe["command"] = self.describeSession
        self.describe.grid(row=2, column=2, padx=2, pady=2)
        self.describe["state"] = "disabled"

        # total time
        self.Totallabel = Label(self.master, width=10,
                                padx=5, pady=5, bd=0, text="00:00:00")
        self.Totallabel.grid(row=1, column=2, columnspan=1, padx=5, pady=5)

        # Create Fastforward button
        self.imageright = PhotoImage(file="icon/right.png")
        self.right = Button(self.master, width=30, padx=2, pady=2, bd=0)
        self.right['image'] = self.imageright
        self.right["command"] = self.fastForward
        self.right.grid(row=1, column=3, columnspan=1, padx=2, pady=2)

        # Create Backward button
        self.imageleft = PhotoImage(file="icon/left.png")
        self.left = Button(self.master, width=30, padx=2, pady=2, bd=0)
        self.left['image'] = self.imageleft
        self.left["command"] = self.fastBackward
        self.left.grid(row=1, column=0, columnspan=1, padx=2, pady=2)

        # Create nextVideo button
        self.next = Button(self.master, width=15, padx=3, pady=3)
        self.next["text"] = "Next"
        self.next["command"] = self.nextMovie
        self.next.grid(row=3, column=3, padx=2, pady=2)
        self.next["state"] = "disabled"

        # Create backVideo button
        self.back = Button(self.master, width=15, padx=3, pady=3)
        self.back["text"] = "Back"
        self.back["command"] = self.backMovie
        self.back.grid(row=3, column=0, padx=2, pady=2)
        self.back["state"] = "disabled"

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

        # set total time
        self.totalTime = self.getDurationTime()
        self.Totallabel.config(text=self.totalTime)

    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)

        if self.frameNbr != 0:
            lossRate = self.lossCounter / self.frameNbr
            print("[*]RTP Packet Loss Rate: " + str(lossRate) + "\n")

        self.master.destroy()  # Close the gui window
        # Delete the cache image from video
        if self.cache:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
            self.cache = False

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            # Create a new thread to listen for RTP packets
            threading.Thread(target=self.listenRtp).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)
            self.cache = True

    def describeSession(self):
        """Describe button handler."""
        self.sendRtspRequest(self.DESCRIBE)

    def fastForward(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.FASTFORWARD)

    def fastBackward(self):
        frame_return = 3 * 20
        if self.state == self.PLAYING:
            if self.frameNbr <= frame_return:
                self.frameNbr = 0
            else:
                self.frameNbr -= frame_return

            self.sendRtspRequest(self.BACKWARD)

    # next video
    def nextMovie(self):
        # get next video
        NEXT = 1

        if self.cache:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
            self.cache = False
        self.fileName = self.findMovie(NEXT)
        self.sendRtspRequest(self.NEXT)
        self.teardownAcked = 0
        self.frameNbr = 0

    # back video
    def backMovie(self):
        # get next video
        BACK = 0

        if self.cache:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
            self.cache = False
        self.fileName = self.findMovie(BACK)
        self.sendRtspRequest(self.BACK)
        self.teardownAcked = 0
        self.frameNbr = 0

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    # If sequence number doesn't match, we have a packet loss
                    if self.frameNbr + 1 != rtpPacket.seqNum():
                        self.lossCounter += (rtpPacket.seqNum() -
                                             (self.frameNbr + 1))
                        print("[*]Packet loss!")

                    currFrameNbr = rtpPacket.seqNum()
                    print("Current Seq Num: " + str(currFrameNbr))

                    if currFrameNbr > self.frameNbr:  # Discard the late packet
                        # Count the received bytes
                        self.bytesReceived += len(rtpPacket.getPayload())

                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(
                            rtpPacket.getPayload()))

                        # Show the current streaming time
                        currentTime = int(currFrameNbr * 0.05)
                        self.timeBox.configure(text="%02d:%02d" % (
                            currentTime // 60, currentTime % 60))

            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet():
                    break

                # Upon receiving ACK for TEARDOWN request,
                # close the RTP socket
                if self.requestSent == self.TEARDOWN:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()

        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=288)
        self.label.image = photo

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkinter.messagebox.showwarning(
                'Connection Failed', 'Connection to \'%s\' failed.' % self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # -------------
        # TO COMPLETE
        # -------------

        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            # Update RTSP sequence number.
            self.rtspSeq = 1

            # Write the RTSP request to be sent.
            request = "SETUP " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Transport: RTP/UDP; client_port= " + str(self.rtpPort)

            # Keep track of the sent request.
            self.requestSent = self.SETUP

        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "PLAY " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.PLAY

        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "PAUSE " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.PAUSE

        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "TEARDOWN " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.TEARDOWN

        # Describe request
        elif requestCode == self.DESCRIBE and not self.state == self.INIT:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "DESCRIBE " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.DESCRIBE

        #  Fast Forward request
        elif requestCode == self.FASTFORWARD and self.state == self.PLAYING:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "FASTFORWARD " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.FASTFORWARD

        # Backward request
        elif requestCode == self.BACKWARD and (self.state == self.PLAYING or self.state == self.PAUSE):
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "BACKWARD " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.BACKWARD

        # next request
        elif requestCode == self.NEXT:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "NEXT " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.NEXT

        # next request
        elif requestCode == self.BACK:
            # Update RTSP sequence number.
            self.rtspSeq += 1

            # Write the RTSP request to be sent.
            request = "BACK " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)

            # Keep track of the sent request.
            self.requestSent = self.BACK

        else:
            return

        # Send the RTSP request using rtspSocket.
        self.rtspSocket.send(request.encode())

        print('\nData sent:\n' + request)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                self.parseRtspReply(reply.decode("utf-8"))

            # Close the RTSP socket upon requesting Teardown
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break

            # if self.teardownAcked == 1:
            #     os.remove(CACHE_FILE_NAME +
            #               str(self.sessionId) + CACHE_FILE_EXT)
            #     self.rtspSocket.shutdown(socket.SHUT_RDWR)
            #     self.rtspSocket.close()
            #     break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        lines = data.split('\n')
        seqNum = int(lines[1].split(' ')[1])

        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session

            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200:
                    if self.requestSent == self.SETUP:
                        # -------------
                        # TO COMPLETE
                        # -------------
                        # Update RTSP state.
                        self.state = self.READY

                        # Open RTP port.
                        self.openRtpPort()

                        # Update buttons' states
                        self.setup["state"] = "disabled"
                        self.start["state"] = "normal"
                        self.pause["state"] = "disabled"
                        self.teardown["state"] = "normal"
                        self.describe["state"] = "normal"
                        self.next["state"] = "disabled"
                        self.back["state"] = "disabled"

                    elif self.requestSent == self.PLAY:
                        # Update RTSP state.
                        self.state = self.PLAYING

                        # Start counting received bytes
                        self.startTime = time.time()
                        self.bytesReceived = 0

                        # Update buttons' states
                        self.setup["state"] = "disabled"
                        self.start["state"] = "disabled"
                        self.pause["state"] = "normal"
                        self.teardown["state"] = "normal"
                        self.next["state"] = "normal"
                        self.back["state"] = "normal"

                    elif self.requestSent == self.PAUSE:
                        # Update RTSP state.
                        self.state = self.READY

                        # The play thread exits. A new thread is created on resume.
                        self.playEvent.set()

                        # Calculate the video data rate
                        dataRate = int(self.bytesReceived /
                                       (time.time() - self.startTime))
                        print("[*]Video data rate: " +
                              str(dataRate) + " bytes/sec\n")

                        # Update buttons' states
                        self.setup["state"] = "disabled"
                        self.start["state"] = "normal"
                        self.pause["state"] = "disabled"
                        self.teardown["state"] = "normal"
                        self.next["state"] = "normal"
                        self.back["state"] = "normal"

                    elif self.requestSent == self.TEARDOWN:
                        # Update RTSP state.
                        self.state = self.INIT

                        # Flag the teardownAcked to close the socket.
                        self.teardownAcked = 1

                    elif self.requestSent == self.DESCRIBE:
                        # Write RTSP payload to session file
                        f = open(SESSION_FILE, "w")
                        for i in range(4, len(lines)):
                            f.write(lines[i] + '\n')
                        f.close()

                    elif self.requestSent == self.NEXT:
                        # self.openRtpPort()
                        self.state = self.READY
                        self.setup["state"] = "disabled"
                        self.start["state"] = "normal"
                        self.pause["state"] = "disabled"
                        self.teardown["state"] = "normal"
                        self.describe["state"] = "normal"
                        self.next['state'] = 'normal'
                        self.back["state"] = "normal"

                    elif self.requestSent == self.BACK:
                        # self.openRtpPort()
                        self.state = self.READY
                        self.setup["state"] = "disabled"
                        self.start["state"] = "normal"
                        self.pause["state"] = "disabled"
                        self.teardown["state"] = "normal"
                        self.describe["state"] = "normal"
                        self.next['state'] = 'normal'
                        self.back["state"] = "normal"

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # -------------
        # TO COMPLETE
        # -------------
        # Create a new datagram socket to receive RTP packets from the server
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)

        try:
            # Bind the socket to the address using the RTP port given by the client user
            self.rtpSocket.bind(("", self.rtpPort))
        except:
            tkinter.messagebox.showwarning(
                'Unable to Bind', 'Unable to bind PORT=%d' % self.rtpPort)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()

    def getDurationTime(self):
        video = VideoStream(self.fileName)
        while video.nextFrame():
            pass
        totalFrame = video.frameNbr()
        seconds = totalFrame * 0.05
        video_time = str(timedelta(seconds=seconds))
        return video_time
        # fps = 20 # Declare in ServerWorker.py sendRtp() function | fps = 1/0.05
        # seconds = totalFrame / fps
        # video_time = str(timedelta(seconds=seconds))
        # return video_time

    # find next video
    def findMovie(self, status):
        NEXT = 1
        BACK = 0

        # Get list video
        videoList = []
        for root, dirs, files in os.walk('./'):
            for name in files:
                if fnmatch.fnmatch(name, '*.Mjpeg'):
                    videoList.append(os.path.join(root, name))

        # find next video
        numVideo = len(videoList)
        for i in range(numVideo):
            if (i == self.curVideo):
                if (status == NEXT):
                    if (i == numVideo - 1):
                        self.curVideo = 0
                    else:
                        self.curVideo = i+1
                elif (status == BACK):
                    if (i == 0):
                        self.curVideo = numVideo-1
                    else:
                        self.curVideo = i-1
                newVideo = videoList[self.curVideo]
                break
        return newVideo
