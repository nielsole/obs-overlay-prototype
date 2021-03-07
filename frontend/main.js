var d = new Date();
var n = d.getTime();
qrcode = new QRCode(document.getElementById("qrcode"), "" + n);

function generateQRCode() {
    var d = new Date();
    var n = d.getTime();
    qrcode.clear()
    qrcode.makeCode("" + n)
    console.log("Set QR code to time" + n)
    return qrcode
}
setInterval(generateQRCode, 500);
