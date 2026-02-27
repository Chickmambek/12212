# Python script to check if the word 'witch' is in the BIP39 wordlist

def load_bip39_wordlist(file_path):
    """
    Load the BIP39 wordlist from a file.
    Args:
    - file_path (str): The path to the wordlist file.

    Returns:
    - set: A set of words from the wordlist.
    """
    with open(file_path, 'r') as file:
        wordlist = set(file.read().splitlines())
    return wordlist


def is_word_in_bip39(word, wordlist):
    """
    Check if the word exists in the BIP39 wordlist.
    Args:
    - word (str): The word to check.
    - wordlist (set): The set containing words from the BIP39 wordlist.

    Returns:
    - bool: True if the word is in the wordlist, otherwise False.
    """
    return word.lower() in wordlist


# Example usage
if __name__ == "__main__":
    # Path to the BIP39 wordlist file
    bip39_file_path = 'bip39_wordlist.txt'  # Replace with the actual path to your BIP39 wordlist file

    # Load the wordlist
    bip39_words = load_bip39_wordlist(bip39_file_path)

    # Word to check
    word_to_check = 'witch'

    # Check if the word is in the wordlist
    if is_word_in_bip39(word_to_check, bip39_words):
        print(f"'{word_to_check}' is in the BIP39 wordlist.")
    else:
        print(f"'{word_to_check}' is NOT in the BIP39 wordlist.")
