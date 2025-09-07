import qrcode

# QR ke andar jo data rakhna ho (jaise text, link, ya attendance info)
data = "Hello Krishna, QR code generated successfully!"

# QR code object banao
qr = qrcode.QRCode(
    version=1,  # size (1=smallest)
    box_size=10,  # har box ka size
    border=5     # border ka thickness
)

qr.add_data(data)
qr.make(fit=True)

# QR ko image me convert karo
img = qr.make_image(fill_color="black", back_color="white")

# file me save karo
img.save("my_qr.png")

print("QR code generated → 'my_qr.png' file me save ho gaya ✅")
