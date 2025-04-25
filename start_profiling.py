"""Starts the GUI."""
import cProfile
import os
import pstats

import debugpy  # Ensures debugger attaches

from esibd.__main__ import main

if __name__ == "__main__":
    debugpy.listen(5678)  # Match the port in your VS Code launch config
    debugpy.wait_for_client()  # Wait for the debugger to attach
    print("Debugger attached")

    try:
        # Profile the main function
        profiler = cProfile.Profile()
        profiler.enable()
        main()
        profiler.disable()
        # Save profile stats
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Saving profile to:", os.getcwd())
        print("Disabling profiler and saving stats")
        profiler.disable()
        with open("output.prof", "w") as file:
            print("Writing stats to file...")
            stats = pstats.Stats(profiler, stream=file)
            stats.strip_dirs()
            stats.sort_stats("cumulative")
            stats.print_stats()
        print("Stats written successfully.")
