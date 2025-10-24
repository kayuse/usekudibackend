for length in range(1, 10):  # from 1-digit up to 9-digits
    for i in range(10**length):
        s = str(i).zfill(length)
        print(s)
