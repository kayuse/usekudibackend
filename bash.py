import mailtrap as mt

mail = mt.Mail(
    sender=mt.Address(email="hello@usekudi.com", name="Mailtrap Test"),
    to=[mt.Address(email="ilanaa.soft@gmail.com")],
    subject="You are awesome!",
    html="Congrats for sending test email with Mailtrap!",
    category="Integration Test",
)

client = mt.MailtrapClient(token="<YOUR_API_TOKEN>")
response = client.send(mail)

print(response)