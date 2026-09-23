import time


def main():
    total_seconds = 50 * 60

    while total_seconds >= 0:
        minutes, seconds = divmod(total_seconds, 60)
        print(f"Timer: {minutes:02d}:{seconds:02d}", flush=True)

        if total_seconds == 0:
            break

        time.sleep(1)
        total_seconds -= 1


if __name__ == "__main__":
    main()
