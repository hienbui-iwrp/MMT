class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0
        self.frameLengthList = []
        self.fast_forward = 0
        self.fast_backward = 0

    def fastForward(self):
        self.fast_forward = 1

    def fastBackward(self):
        self.fast_backward = 1

    def nextFrame(self):

        if self.fast_forward:
            prevData = None
            for i in range(3 * 20):
                data = self.file.read(5)
                if data:
                    framelength = int(data)
                    data = self.file.read(framelength)
                    self.frameNum += 1
                    if self.frameNum > len(self.frameLengthList):
                        self.frameLengthList.append(framelength)
                    prevData = data
                else:
                    self.fast_forward = 0
                    return prevData
            self.fast_forward = 0
            return data

        if self.fast_backward:
            numFrame = 3 * 20
            if numFrame >= self.frameNum:
                self.file.seek(0, 0)
                self.frameNum = 0
            else:
                for i in range(numFrame):
                    self.frameNum -= 1
                    self.file.seek(-5 - self.frameLengthList[self.frameNum], 1)

            self.fast_backward = 0

        """Get next frame."""
        data = self.file.read(5)  # Get the framelength from the first 5 bits
        if data:
            framelength = int(data)
            data = self.file.read(framelength)
            self.frameNum += 1
            if self.frameNum >= len(self.frameLengthList):
                self.frameLengthList.append(framelength)
        return data

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum
