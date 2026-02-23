
# AI Financial Research Agent

An AI agent for real-time stock research and financial analysis, built with LangChain and OpenAI.

## The Features
- Real-time stock price lookup (via yfinance)
- P/E ratio calculator
- Web search integration (via SerpAPI)
- Interactive REPL or single-question mode
- Fully configurable agent name

## What it Requires
- Python 3.10+
- OpenAI API key
- SerpAPI key (optional, for web search)

## The Setup

### 1. Clone the repo
git clone https://github.com/HELLO-AMHANI/ai-agent.git
cd ai-agent

### 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # for mac/linux
.\venv\Scripts\Activate.ps1    # for windows

### 3. Install dependencies
pip install -r requirements.txt

### 4. Configure environment variables
Create a `.env` file in the root folder:
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
AGENT_NAME=YourAgentName
SERPAPI_API_KEY=your-key-here   # it's optional

## Usage

### Interactive mode
python agent.py --repl

### Single question
python agent.py --ask "Get stock price for AAPL"

### With verbose reasoning
python agent.py --repl --verbose

### Custom name
python agent.py --repl --name "AMHANi"

## Example Questions
- "Get me the stock price of TSLA"
- "What is the PE ratio for a stock priced at 200 with EPS of 10"
- "Search for latest news on Apple earnings"

## Project Structure
ai-agent/
├── agent.py          # Main CLI agent
├── tools.py          # Tool definitions (stock, PE ratio)
├── requirements.txt
├── .env              # Never committed — contains your API keys
├── .gitignore
├── README.md
├── .github/
│   └── workflows/
│       └── ci.yml   # GitHub Actions CI
└── tests/
    └── smoke_test.py

## Tech Stack
- [LangChain](https://langchain.com) — Agent framework
- [OpenAI](https://openai.com) — LLM (gpt-5-mini)
- [yfinance](https://github.com/ranaroussi/yfinance) — Stock data
- [SerpAPI](https://serpapi.com) — Web search
