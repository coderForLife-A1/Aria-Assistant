import os
from langchain_openai import ChatOpenAI
from crewai import Task, Crew, Process

from agents import create_aria_router, create_news_agent, create_dev_agent

# ==========================================
# Phase 1: Environment & Engine Initialization
# ==========================================

# 1. Load the OpenAI API key securely
api_key = os.getenv("OPENAI_API_KEY")

# 2. Write explicit error handling
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is missing. Please set it before running.")

# 3. Initialize the gpt-4o-mini LLM engine
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    api_key=api_key
)

# ==========================================
# Phase 2: Agent Construction
# ==========================================

aria_router = create_aria_router(llm)
news_agent = create_news_agent(llm)
dev_agent = create_dev_agent(llm)

# ==========================================
# Phase 3: Task Definition
# ==========================================

# 1. Define a task based on the user request
introduction_task = Task(
    description="Aria, introduce me to your team. Ask the News Agent and the Dev Agent to explain what they do and what they are experts in.",
    expected_output="A structured introduction containing a greeting from Aria, followed by detailed explanations from the Global News Agent and the Senior Dev Agent about their roles, expertise, and capabilities.",
    agent=aria_router,
)

# ==========================================
# Phase 4: Crew Orchestration
# ==========================================

# 1. Assemble the agents and tasks into a Crew object
# 2. Set the process to Process.sequential
aria_crew = Crew(
    agents=[aria_router, news_agent, dev_agent],
    tasks=[introduction_task],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    print("Initiating Aria Crew Workflow...\n")
    
    # 3. Execute the kickoff() method
    result = aria_crew.kickoff()
    
    # 4. Print the final output cleanly to the console
    print("\n==========================================")
    print("FINAL OUTPUT:")
    print("==========================================")
    print(result)
