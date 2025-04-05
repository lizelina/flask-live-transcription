let isRecording = false;
let socket;
let microphone;
let reconnectAttempts = 0;
let deepgramConnected = false;
const MAX_RECONNECT_ATTEMPTS = 5;

const socket_port = 5001;

function initializeSocket() {
  socket = io(
    "http://" + window.location.hostname + ":" + socket_port.toString(),
    {
      reconnection: true,           // Enable reconnection
      reconnectionAttempts: 5,      // Try to reconnect 5 times
      reconnectionDelay: 1000,      // Wait 1s before reconnect attempt
      reconnectionDelayMax: 5000,   // Max wait time between attempts
      timeout: 20000                // Longer connection timeout
    }
  );

  // Connection status debugging
  socket.on('connect', () => {
    console.log('Connected to socket server');
    reconnectAttempts = 0;
    document.getElementById("captions").innerHTML = "Socket connected. Click the microphone to start.";
  });

  socket.on('disconnect', () => {
    console.log('Disconnected from socket server');
    deepgramConnected = false;
    document.getElementById("captions").innerHTML = "Socket disconnected. Attempting to reconnect...";
    
    // If we were recording, stop the recording
    if (isRecording) {
      stopRecording(true); // true = silent mode (don't emit to server)
    }
  });

  socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
    reconnectAttempts++;
    document.getElementById("captions").innerHTML = `Error connecting to server: ${error.message}. Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`;
    
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      document.getElementById("captions").innerHTML = "Could not connect to server. Please refresh the page to try again.";
    }
  });

  socket.on('reconnect', (attemptNumber) => {
    console.log(`Reconnected on attempt ${attemptNumber}`);
    document.getElementById("captions").innerHTML = "Reconnected to server. Click the microphone to start again.";
  });

  socket.on('server_status', (data) => {
    console.log('Server status:', data);
  });

  socket.on('deepgram_ready', (data) => {
    console.log('Deepgram connection ready:', data);
    deepgramConnected = true;
    document.getElementById("captions").innerHTML = "Listening... Speak now";
  });

  socket.on('deepgram_stopped', (data) => {
    console.log('Deepgram stopped:', data);
    deepgramConnected = false;
    
    // If we're still recording for some reason, make sure we stop
    if (isRecording) {
      stopRecording(true);
    }
    
    document.getElementById("captions").innerHTML = "Transcription stopped";
  });

  socket.on('deepgram_disconnected', (data) => {
    console.log('Deepgram disconnected:', data);
    deepgramConnected = false;
    if (isRecording) {
      stopRecording(true);
      document.getElementById("captions").innerHTML = "Deepgram disconnected. Please try again.";
    }
  });

  socket.on('deepgram_error', (data) => {
    console.error('Deepgram error:', data);
    document.getElementById("captions").innerHTML = "Error with speech service: " + data.error;
  });

  socket.on('connection_lost', (data) => {
    console.error('Connection lost:', data);
    deepgramConnected = false;
    document.getElementById("captions").innerHTML = data.message;
    
    // If we're still recording, stop
    if (isRecording) {
      stopRecording(true);
    }
  });

  socket.on('connection_error', (data) => {
    console.error('Connection error:', data);
    document.getElementById("captions").innerHTML = data.message;
  });

  socket.on("transcription_update", (data) => {
    console.log("Received transcription:", data.transcription);
    document.getElementById("captions").innerHTML = data.transcription;
  });
}

async function getMicrophone() {
  try {
    console.log("Requesting microphone access...");
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        channelCount: 1,       // Mono audio (required by Deepgram)
        sampleRate: 16000,     // 16 kHz sample rate
        echoCancellation: true, // Improve audio quality
        noiseSuppression: true  // Improve audio quality
      } 
    });
    console.log("Microphone access granted", stream);
    
    // Check for supported formats
    const supportedFormats = [];
    if (MediaRecorder.isTypeSupported('audio/webm')) supportedFormats.push('audio/webm');
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) supportedFormats.push('audio/webm;codecs=opus');
    if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) supportedFormats.push('audio/ogg;codecs=opus');
    if (MediaRecorder.isTypeSupported('audio/mp4')) supportedFormats.push('audio/mp4');
    console.log("Supported audio formats:", supportedFormats);
    
    // Choose the best format
    let mimeType = supportedFormats[0] || '';
    console.log("Using MIME type:", mimeType);
    
    // Create MediaRecorder with best available format
    const recorder = new MediaRecorder(stream, { 
      mimeType: mimeType,
      audioBitsPerSecond: 16000  // 16 kbps audio
    });
    
    // Log MediaRecorder properties
    console.log("MediaRecorder created:", {
      mimeType: recorder.mimeType,
      state: recorder.state,
      audioBitsPerSecond: recorder.audioBitsPerSecond,
      videoBitsPerSecond: recorder.videoBitsPerSecond
    });
    
    return recorder;
  } catch (error) {
    console.error("Error accessing microphone:", error);
    document.getElementById("captions").innerHTML = "Error accessing microphone: " + error.message;
    throw error;
  }
}

async function openMicrophone(microphone, socket) {
  return new Promise((resolve) => {
    microphone.onstart = () => {
      console.log("Client: Microphone opened");
      document.body.classList.add("recording");
      resolve();
    };
    
    let packetCount = 0;
    let totalBytes = 0;
    
    microphone.ondataavailable = async (event) => {
      // Only process audio data if still recording
      if (isRecording && event.data.size > 0) {
        packetCount++;
        totalBytes += event.data.size;
        
        // Only log occasionally to reduce console spam
        if (packetCount % 10 === 0) {
          console.log(`Audio stats: ${packetCount} packets, ${(totalBytes/1024).toFixed(2)} KB total`);
        }
        
        // Only send if we're still recording
        if (isRecording && socket && socket.connected) {
          socket.emit("audio_stream", event.data);
        }
      } else if (!isRecording) {
        console.log("Ignoring audio data after recording stopped");
      } else if (event.data.size === 0) {
        console.warn("Empty audio packet received");
      }
    };
    
    microphone.onstop = () => {
      console.log("MediaRecorder stopped");
      // Ensure we mark recording as false when MediaRecorder stops
      isRecording = false;
    };
    
    microphone.onerror = (event) => {
      console.error("Microphone error:", event.error);
      isRecording = false;
      document.getElementById("captions").innerHTML = "Microphone error: " + event.error;
    };
    
    // Use a smaller interval for more frequent packets
    console.log("Starting MediaRecorder with 500ms interval");
    microphone.start(500);
  });
}

async function startRecording() {
  isRecording = true;
  document.getElementById("captions").innerHTML = "Initializing microphone...";
  
  try {
    microphone = await getMicrophone();
    console.log("Client: Waiting to open microphone");
    await openMicrophone(microphone, socket);
    document.getElementById("captions").innerHTML = "Connecting to Deepgram...";
    
    // Only if socket is connected
    if (socket && socket.connected) {
      socket.emit("toggle_transcription", { action: "start" });
    } else {
      throw new Error("Socket not connected, can't start transcription");
    }
  } catch (error) {
    isRecording = false;
    document.getElementById("captions").innerHTML = "Error starting recording: " + error.message;
  }
}

async function stopRecording(silent = false) {
  if (isRecording === true) {
    console.log("Stopping microphone");
    
    // First, signal the server to stop transcription
    if (!silent && socket && socket.connected) {
      console.log("Sending stop signal to server");
      socket.emit("toggle_transcription", { action: "stop" });
    }
    
    // Set recording state to false IMMEDIATELY to prevent any new packets from being sent
    isRecording = false;
    
    // Then stop the microphone
    if (microphone) {
      try {
        // Stop data collection first
        console.log("Stopping MediaRecorder");
        microphone.stop();
        
        // Then stop all tracks to fully release the microphone
        if (microphone.stream) {
          console.log("Stopping all audio tracks");
          microphone.stream.getTracks().forEach((track) => {
            console.log(`Stopping track: ${track.kind} (${track.id})`);
            track.stop();
          });
        }
      } catch (e) {
        console.error("Error stopping microphone:", e);
      }
    }
    
    // Clear the reference to prevent any chance of reuse
    microphone = null;
    
    console.log("Client: Microphone closed");
    document.body.classList.remove("recording");
    
    if (!silent) {
      document.getElementById("captions").innerHTML = "Recording stopped";
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const recordButton = document.getElementById("record");
  document.getElementById("captions").innerHTML = "Connecting to server...";
  
  // Initialize the socket connection
  initializeSocket();

  recordButton.addEventListener("click", () => {
    if (!socket || !socket.connected) {
      console.log("Socket not connected, attempting to reconnect");
      socket.connect();
      document.getElementById("captions").innerHTML = "Reconnecting to server...";
      return;
    }
    
    if (!isRecording) {
      console.log("Starting recording process");
      startRecording().catch((error) => {
        console.error("Error starting recording:", error);
        document.getElementById("captions").innerHTML = "Error: " + error.message;
      });
    } else {
      console.log("Stopping recording process");
      stopRecording().catch((error) => {
        console.error("Error stopping recording:", error);
        document.getElementById("captions").innerHTML = "Error stopping: " + error.message;
      });
    }
  });
});
