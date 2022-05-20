import os, time, json, sys
import numpy as np
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets

#from threading import Lock

from mrigtlbridge.listener_base import ListenerBase
from mrigtlbridge import common
from mrigtlbridge.common import DataTypeTable
import openigtlink as igtl

from queue import Queue

# Data Converter thread
# We need this thread since the listener thread cannot catch up with the Example
class ExampleToIGTLThread(QtCore.QThread):

  def __init__(self, *args):
    super().__init__(*args)
    
    self.messageQueue = Queue(maxsize = 100)
    self.active = True
    self.signalManager = None
    self.currentImageType = None
    self.mutex = QtCore.QMutex()
      
  def __del__(self):
    del self.mutex

  
  def setSignalManager(self, sm):
    self.signalManager = sm
  
  
  def stop(self):
    self.active = False

    
  def run(self):

    while self.active:
      if self.messageQueue.empty():
        QtCore.QThread.msleep(10) # wait for 10 ms
        continue

      st = time.time()
      self.mutex.lock()
      data =  self.messageQueue.get()
      self.convert(data)
      self.mutex.unlock()
      ed = time.time()
      
      print('convert %f' % (ed-st))
      

      
  def enqueue(self, data):
    if self.messageQueue.full():
      return False
    self.mutex.lock()
    self.messageQueue.put(data)
    self.mutex.unlock()
    return True


  def convert(self, data):
    
    name = data[1]
    images = data[0]
    
    if images[0]:
      imageGroups = self.groupSlicesByOrientation(images)
      for key, group in imageGroups.items():
        groupName = name + ' ' + str(key)
        self.sendSliceGroup(group, groupName)

      
  def groupSlicesByOrientation(self,data):
    # This function checks the slice orientation of each image in the given dictionary ('images')
    # and group them, when there are multiple slice groups in a series (e.g., a series produced
    # by a 3-plane localizer protocol). Returns a dictionary of image arrays (e.g., 
    # {0: [images[0], images[1], images[2]],   # Slice group #0
    #  1: [images[3], images[4], images[5]],   # Slice group #1
    #  2: [images[6], images[7], images[8]]}   # Slice group #3
    
    # NOTE: The function does not work if the groups have a same slice orientation.

    sliceDicTemp = {}
    for key, image in data.items():
      coordinates = image["value"]["image"]["coordinates"]["mrSlicePcs"]    
      norm_x = coordinates["normal"]["sag"]
      norm_y = coordinates["normal"]["cor"]
      norm_z = coordinates["normal"]["tra"]
      
      # Generate a key unique to the slice orientation
      sliceKey = str(norm_x)+','+str(norm_y)+','+str(norm_z)
      if not sliceKey in sliceDicTemp:
        sliceDicTemp[sliceKey] = []
      sliceDicTemp[sliceKey].append(image)

    groups = {}
    index = 0
    for key, imageList in sliceDicTemp.items():
      groups[index] = imageList
      index = index + 1

    return groups

    
  def sendSliceGroup(self, images, name):

    # TODO: Sometimes, it receives junk data.. skip if it happens.
    if type(images[0]["value"]["image"]["data"]) is str:
      return
    
    param = {}
        
    dimensions = images[0]["value"]["image"]["dimensions"]
    columns = int(dimensions["columns"])
    rows = int(dimensions["rows"])
    slices = len(images)

    voxelSizes = images[0]["value"]["image"]["dimensions"]["voxelSize"]
    colSpacing = float(voxelSizes["column"])
    rowSpacing = float(voxelSizes["row"])
    sliceSpacing = float(voxelSizes["slice"])  # Should be calculated from the slice positions for volume

    #dtypeTable = {
    #  'int8':    [2, 1],   #TYPE_INT8    = 2, 1 byte
    #  'uint8':   [3, 1],   #TYPE_UINT8   = 3, 1 byte
    #  'int16':   [4, 2],   #TYPE_INT16   = 4, 2 bytes
    #  'uint16':  [5, 2],   #TYPE_UINT16  = 5, 2 bytes
    #  'int32':   [6, 4],   #TYPE_INT32   = 6, 4 bytes
    #  'uint32':  [7, 4],   #TYPE_UINT32  = 7, 4 bytes
    #  'float32': [10,4],   #TYPE_FLOAT32 = 10, 4 bytes 
    #  'float64': [11,8],   #TYPE_FLOAT64 = 11, 8 bytes
    #}

    scalarSize = 2
    dtypeName = images[0]["value"]["image"]["data"].pixel_array.dtype.name

    if dtypeName in DataTypeTable:
      #imageMsg.SetScalarType(dtypeTable[dtypeName][0])
      #scalarSize = dtypeTable[dtypeName][1]
      scalarSize = DataTypeTable[dtypeName][1]
      
    # Check slice positions and sort
    imagesByDist = {}

    # First slice
    position = images[0]["value"]["image"]["coordinates"]["mrSlicePcs"]["position"]
    x = -float(position["sag"])
    y = -float(position["cor"])
    z = float(position["tra"])
    posFirst = np.array([x, y, z])
    imagesByDist[0.0] = (images[0], posFirst)
    print('position = ' + str(posFirst))
    
    if slices > 1:

      # Second slice
      position = images[1]["value"]["image"]["coordinates"]["mrSlicePcs"]["position"]
      x = -float(position["sag"])
      y = -float(position["cor"])
      z = float(position["tra"])
      posSecond = np.array([x, y, z])
      vec1 = posSecond-posFirst
      dist = np.linalg.norm(vec1)
      vec1 = vec1/dist # normalize
      imagesByDist[dist] = (images[1], posSecond)
      
      if slices > 2:

        # Sort slices
        for i in range(1, slices):
          im = images[i]
          coordinates = im["value"]["image"]["coordinates"]["mrSlicePcs"]
          position = coordinates["position"]
          x = -float(position["sag"])
          y = -float(position["cor"])
          z = float(position["tra"])
          pos = np.array([x, y, z])
          print(pos)
          vec = pos-posFirst
          dist = np.linalg.norm(vec)
          vec = vec/dist
          sign = np.inner(vec, vec1)
          dist = sign * dist
          imagesByDist[dist] = (im, pos)
        
      
    distList = sorted(imagesByDist)
    print(distList)
    
    posFirst = imagesByDist[distList[0]][1]
    posLast = imagesByDist[distList[-1]][1]
    maxDistance = np.linalg.norm(posLast-posFirst)

    binary = []
    binaryOffset = []

    # Package image data for OpenIGT by packing as C array
    offset = 0
    #for i in range(slices):
    for dist in distList:
      im = imagesByDist[dist][0]
      if type(im["value"]["image"]["data"]) is str:
        return
      if im["value"]["image"]["data"].pixel_array.dtype.name != 'uint16':
        return
      binary.append(im["value"]["image"]["data"].pixel_array)
      binaryOffset.append(offset)
      offset = offset + columns*rows*scalarSize;

    # For a volume, calculate slice spacing based on the center positions
    if slices > 1:
      sliceSpacing = maxDistance / float(slices-1)
      
    #imageMsg.SetSpacing(colSpacing, rowSpacing, sliceSpacing)
      
    rawMatrix = [[0.0,0.0,0.0,0.0],
                 [0.0,0.0,0.0,0.0],
                 [0.0,0.0,0.0,0.0],
                 [0.0,0.0,0.0,1.0]]

    # Create C array for coordinates
    coordinates = images[0]["value"]["image"]["coordinates"]["mrSlicePcs"]
    position = coordinates["position"]
    
    if slices > 1:
      posCenter = (posFirst + posLast) / 2.0
      rawMatrix[0][3] = posCenter[0]
      rawMatrix[1][3] = posCenter[1]
      rawMatrix[2][3] = posCenter[2]
    else:
      rawMatrix[0][3] = posFirst[0]
      rawMatrix[1][3] = posFirst[1]
      rawMatrix[2][3] = posFirst[2]
      
    X = [[0.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]]

    X[0][0] = float(coordinates["read"]["sag"])
    X[1][0] = float(coordinates["read"]["cor"])
    X[2][0] = float(coordinates["read"]["tra"])
    X[0][1] = float(coordinates["phase"]["sag"])
    X[1][1] = float(coordinates["phase"]["cor"])
    X[2][1] = float(coordinates["phase"]["tra"])        
    X[0][2] = float(coordinates["normal"]["sag"])
    X[1][2] = float(coordinates["normal"]["cor"])
    X[2][2] = float(coordinates["normal"]["tra"])
    igtl.PrintMatrix(X)
    
    rawMatrix[0][0] = -float(coordinates["read"]["sag"])
    rawMatrix[1][0] = -float(coordinates["read"]["cor"])
    rawMatrix[2][0] = float(coordinates["read"]["tra"])
    #rawMatrix[0][1] = -float(coordinates["phase"]["sag"])
    #rawMatrix[1][1] = -float(coordinates["phase"]["cor"])
    #rawMatrix[2][1] = float(coordinates["phase"]["tra"])        
    rawMatrix[0][2] = -float(coordinates["normal"]["sag"])
    rawMatrix[1][2] = -float(coordinates["normal"]["cor"])
    rawMatrix[2][2] = float(coordinates["normal"]["tra"])

    ### Phase doesn't give correct values
    rawMatrix[0][1] = rawMatrix[1][2]*rawMatrix[2][0] - rawMatrix[1][0]*rawMatrix[2][2]
    rawMatrix[1][1] = rawMatrix[0][0]*rawMatrix[2][2] - rawMatrix[0][2]*rawMatrix[2][0]
    rawMatrix[2][1] = rawMatrix[0][2]*rawMatrix[1][0] - rawMatrix[0][0]*rawMatrix[1][2]
    param['dtype']               = dtypeName
    param['dimension']           = [columns, rows, slices]
    param['spacing']             = [colSpacing, rowSpacing, sliceSpacing]
    param['name']                = name
    param['numberOfComponents']  = 1
    param['endian']              = 2
    param['matrix']              = rawMatrix
    param['attribute']           = {}
    param['binary']              = binary
    param['binaryOffset']        = binaryOffset

    if self.signalManager:
      self.signalManager.emitSignal('sendImageIGTL', param)

    

# ------------------------------------Example------------------------------------
class ExampleListener(ListenerBase):
  #textBoxSignal = QtCore.pyqtSignal(str)
  #imageSignal = QtCore.pyqtSignal(object)
  #streamSignal = QtCore.pyqtSignal(bool)

  def __init__(self, *args):
    super().__init__(*args)

    self.customSignalList = {
      'requestHostControl':  None,
      'releaseHostControl' : None,
      'getTemplatesFromHost' : None,
      'selectTemplate' : 'str',
      'singleSliceMode': 'str', # 'on' or 'off'
      'baselineMode' : 'str', # 'on' or 'off'

      # Following signals are to be connected to the widget slots.
      'hostControlEnabled' : None,
      'hostControlDisabled' : None,
      'hostConnected' : None,
      'hostDisconnected' : None,
      'templatesUpdated' : 'dict',
      'sequenceReady' : None,
      'sequenceNotReady' : None,
      'sequenceStarted' : None
    }

    self.jobQueue = False
    self.counter = 0

    self.baseline = False
    self.singleSlice = False

    self.streaming = False
    
    self.parameter['socketIP'] = ''
    self.parameter['socketPort'] = ''
    self.parameter['licenseFile'] = ''

    #self.converterThread = ExampleToIGTLThread()
    #self.converterThread.start()

  def __del__(self):

    # Destructor
    pass
  
    
  def connectSlots(self, signalManager):
    super().connectSlots(signalManager)
    print('ExampleListener.connectSlots()')
    self.signalManager.connectSlot('startSequence', self.startSequence)
    self.signalManager.connectSlot('stopSequence', self.stopSequence)
    self.signalManager.connectSlot('updateScanPlane', self.updateScanPlane)

    # Define new signals for the scanner
    
    #self.converterThread.setSignalManager(self.signalManager)

    
  def disconnectSlots(self):
    
    super().disconnectSlots()
    
    print('ExampleListener.disconnectSlots()')
    if self.signalManager:
      self.signalManager.disconnectSlot('startSequence', self.startSequence)
      self.signalManager.disconnectSlot('stopSequence', self.stopSequence)
      self.signalManager.disconnectSlot('updateScanPlane', self.updateScanPlane)

    
  def initialize(self):

    # Called when a new listener object is created.
    print('ExampleListener.initialize()')
    
    print('ExampleListener: initializing...')
    socketIP   = str(self.parameter['socketIP'])
    socketPort = str(self.parameter['socketPort'])
    print('  socketIP = ' + socketIP)
    print('  socketPort = ' + socketPort)

    # Establish connection with the scanner, and put the result status in 'ret'
    #ret = self.connect(socketIP, socketPort, licenseFile)
    
    if ret:
      print("ExampleListener: Example connection established.")
      time.sleep(0.5)
      self.signalManager.emitSignal('hostConnected')
      return True
    else:
      print("ExampleListener: Example connection failed.")
      return False
  

  def process(self):
    if self.jobQueue:
      self.startSequence()
      self.jobQueue = False
    #QtCore.QThread.msleep(10)
    QtCore.QThread.msleep(50) # TODO: This may give Example more time to process images 


  def finalize(self):

    # Called the listener is disconnected from the scanner
    print('ExampleListener.finalize()')
    
    self.signalManager.emitSignal('hostDisconnected')

    super().finalize()

  def startSequence(self):

    print('ExampleListener.startSequence()')
    # Called when the user starts the scan either from the GUI or from remote software (e.g., 3D Slicer)

      
  def stopSequence(self):
    print('ExampleListener.stopSequence()')

    # Called when the user stops the scan either from the GUI or from remote software (e.g., 3D Slicer)


  def updateScanPlane(self, param):
    #
    # param['plane_id'] : Plane ID (0, 1, 2, 3, ...)
    # param['matrix'  ] : 4x4 matrix
    #

    matrix4x4 = param['matrix']
    
    # Flip X/Y coordinates (R->L, A->P)
    for i in range(2):
      for j in range(4):
        matrix4x4[i][j] = -matrix4x4[i][j]
        
    matrix = np.array(matrix4x4)

    # Set slice group
    exampleParam={}
    exampleParam['index'] = param['plane_id']

    # Call the scanner command to update the scan plane.
    
    self.signalManager.emitSignal('consoleTextMR', str(matrix))    
    self.signalManager.emitSignal('consoleTextMR', ret)


      
