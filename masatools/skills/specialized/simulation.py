import os
import time

def run_simulation(input_yaml: str) -> str:
    """
    Mock skill for running a numerical simulation.
    In a real agent, this would invoke OpenFOAM, Sdynpy, etc.
    """
    print(f"Starting simulation with input: {input_yaml}")
    # Simulate work
    time.sleep(2)
    return "Simulation completed successfully. Output data generated in local /work directory."
