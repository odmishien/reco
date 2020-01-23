const socket = io.connect('http://' + document.domain + '/record')
let processor = null;
let localstream = null;

function startRecording() {
  // navigator.mediaDevices
  //   .getUserMedia({ audio: true, video: false })
  //   .then(stream => {
  //     localstream = stream;
  //     const input = this.context.createMediaStreamSource(stream);
  //     processor = context.createScriptProcessor(4096, 1, 1);

  //     input.connect(processor);
  //     processor.connect(context.destination);

  //     processor.onaudioprocess = e => {
  //       const voice = e.inputBuffer.getChannelData(0);
  //       socket.emit("send_audio", voice.buffer);
  //     };
  //   })
  //   .catch(e => {
  //     console.log(e);
  //   });
  socket.emit("send_audio", "hoge")
}

function stopRecording() {
  processor.disconnect();
  processor.onaudioprocess = null;
  processor = null;
  localstream.getTracks().forEach(track => {
    track.stop();
  });
  socket.emit("stop", "", res => {
    console.log(`Audio data is saved as ${res.filename}`);
  });
}
