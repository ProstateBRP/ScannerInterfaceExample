from PyQt5 import QtCore, QtGui, QtWidgets


from mrigtlbridge.widget_base  import WidgetBase
import example_listener

class ExampleWidget(WidgetBase):

  def __init__(self, *args):
    super().__init__(*args)
    self.listener_class = ['example_listener', 'ExampleListener']
    self.parent = None
    self.listenerParameter['socketIP']    = '192.168.2.1'
    self.listenerParameter['socketPort']  = '7787'
    

  def buildGUI(self, parent):

    self.parent = parent
    
    layout = QtWidgets.QGridLayout()
    parent.setLayout(layout)

    self.ExampleConnectButton = QtWidgets.QPushButton("Connect to Example")
    self.ExampleConnectButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
    layout.addWidget(self.ExampleConnectButton, 0, 0, 1, 3)
    self.ExampleConnectButton.setEnabled(True)
    #self.ExampleConnectButton.clicked.connect(self.connectExample)
    self.ExampleConnectButton.clicked.connect(self.startListener)
    self.ExampleDisconnectButton = QtWidgets.QPushButton("Disconnect from Example")
    self.ExampleDisconnectButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
    layout.addWidget(self.ExampleDisconnectButton, 0, 3, 1, 3)
    self.ExampleDisconnectButton.setEnabled(False)
    #self.ExampleDisconnectButton.clicked.connect(self.disconnectExample)
    self.ExampleDisconnectButton.clicked.connect(self.stopListener)

    self.Example_IpEdit = QtWidgets.QLineEdit(self.listenerParameter['socketIP'])
    self.Example_IpEdit.textChanged.connect(self.updateListenerParameter)
    layout.addWidget(self.Example_IpEdit, 1, 0, 1, 4)

    self.Example_PortEdit = QtWidgets.QLineEdit(self.listenerParameter['socketPort'])
    self.Example_PortEdit.textChanged.connect(self.updateListenerParameter)
    layout.addWidget(self.Example_PortEdit, 1, 4, 1, 2)

    hline1 = QtWidgets.QFrame()
    hline1.setFrameShape(QtWidgets.QFrame.HLine)
    hline1.setFrameShadow(QtWidgets.QFrame.Sunken)
    layout.addWidget(hline1, 4, 0, 1, 6)        
    
    self.ExampleStartSequenceButton = QtWidgets.QPushButton("Start sequence")
    layout.addWidget(self.ExampleStartSequenceButton, 6, 0, 1, 3)
    self.ExampleStartSequenceButton.clicked.connect(self.startSequenceExample)
    self.ExampleStartSequenceButton.setEnabled(False)
    self.ExampleStopSequenceButton = QtWidgets.QPushButton("Stop sequence")
    layout.addWidget(self.ExampleStopSequenceButton, 6, 3, 1, 3)
    self.ExampleStopSequenceButton.clicked.connect(self.stopSequenceExample)
    self.ExampleStopSequenceButton.setEnabled(False)

    hline2 = QtWidgets.QFrame()
    hline2.setFrameShape(QtWidgets.QFrame.HLine)
    hline2.setFrameShadow(QtWidgets.QFrame.Sunken)
    layout.addWidget(hline2, 7, 0, 1, 6)    

    self.Example_textBox = QtWidgets.QTextEdit()
    self.Example_textBox.setReadOnly(True)
    self.Example_textBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    layout.addWidget(self.Example_textBox, 10, 0, 6, 6)

  def setSignalManager(self, sm):
    super().setSignalManager(sm)
    self.signalManager.connectSlot('consoleTextMR', self.updateExampleBox)
    self.signalManager.connectSlot('hostConnected', self.onHostConnected) # former connectExample()
    self.signalManager.connectSlot('hostDisconnected', self.onHostDisconnected) # former disconnectExample()

    
  def updateGUI(self, state):
    if state == 'listenerConnected':
      pass
    elif state == 'listenerDisconnected':
      pass

    
  def updateListenerParameter(self):

    self.listenerParameter['socketIP']    = self.Example_IpEdit.text()
    self.listenerParameter['socketPort']  = self.Example_PortEdit.text()
    
  def onHostConnected(self):
    try:
      self.updateTemplates()
  
      self.ExampleConnectButton.setEnabled(False)
      self.ExampleDisconnectButton.setEnabled(True)
      self.Example_IpEdit.setEnabled(False)
      self.Example_PortEdit.setEnabled(False)
      self.ExampleStartSequenceButton.setEnabled(True)
      self.ExampleStopSequenceButton.setEnabled(True)
    except:
      print("Failed to connect to Example!")


  def onHostDisconnected(self):
    self.ExampleConnectButton.setEnabled(True)
    self.ExampleDisconnectButton.setEnabled(False)
    self.Example_IpEdit.setEnabled(True)
    self.Example_PortEdit.setEnabled(True)
    self.ExampleStartSequenceButton.setEnabled(False)
    self.ExampleStopSequenceButton.setEnabled(False)

    
  def onSequenceStarted(self):
    print('onSequenceStarted()')
    self.ExampleStartSequenceButton.setEnabled(False)
    self.ExampleStopSequenceButton.setEnabled(True)      

  def updateExampleBox(self, text):
    self.Example_textBox.append(text)

  def startSequenceExample(self):
    self.signalManager.emitSignal('startSequence')

  def stopSequenceExample(self):
    self.signalManager.emitSignal('stopSequence')
    
