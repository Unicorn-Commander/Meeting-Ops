import computer
echo "##active_line2##"
computer.vision.load(load_moondream=True)
echo "##active_line3##"
print("Moondream loaded")
echo "##active_line4##"
result = computer.vision.query("Is this the Unicorn Commander Meeting Ops dashboard or login page? Describe briefly. Be concise.", path="screenshot.png")
echo "##active_line5##"
print(result)
