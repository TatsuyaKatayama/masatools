import os

def analyze_huge_data(query: str) -> str:
    """
    Mock skill for analyzing large datasets residing in the local /work directory.
    """
    print(f"Analyzing data with query: {query}")
    return f"Analysis results for '{query}': Peak value found at step 500."

def generate_summary_plots() -> str:
    """
    Mock skill for generating lightweight summary plots (PNG/PDF) from simulation results.
    """
    print("Generating summary plots...")
    return "Summary plots generated: /work/agent-id/thread-id/output/summary.pdf"
