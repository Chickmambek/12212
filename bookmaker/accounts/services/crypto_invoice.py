import qrcode
import os
import uuid


def generate_payment_qr(address, amount, crypto):
    uri = f"{crypto}:{address}?amount={amount}"

    unique_id = uuid.uuid4().hex  # random unique 32-char string22

    qr = qrcode.make(uri)

    folder = "payment_qr/"
    full_folder = "media/" + folder
    os.makedirs(full_folder, exist_ok=True)

    file_name = f"{crypto}_{unique_id}.png"
    file_path = full_folder + file_name

    # This is what you save in DB
    db_path = folder + file_name

    qr.save(file_path)
    return db_path  # <-------- IMPORTANT
