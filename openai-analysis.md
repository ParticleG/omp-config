## Intelligence vs. Cost per Intelligence Index Task

Artificial Analysis Intelligence Index · Weighted average cost (USD) per Artificial Analysis Intelligence Index task

### Cost per Intelligence Index Task

Weighted average cost per Intelligence Index task. Each evaluation’s cost is calculated from input, cache hit, cache write, reasoning, and answer token prices, divided by task count, and weighted by its Intelligence Index weight.

### Artificial Analysis Intelligence Index

Artificial Analysis Intelligence Index v4.1 includes: GDPval-AA v2, 𝜏³-Banking, Terminal-Bench v2.1, SciCode, Humanity's Last Exam, GPQA Diamond, CritPt, AA-Omniscience, AA-LCR. See Intelligence Index methodology for further details, including a breakdown of each evaluation and how we run them.

### Data Table

| Model              | Cost Per Task | Intelligence Index |
| ------------------ | ------------- | ------------------ |
| gpt-5.6-luna:high  | $0.09         | 46                 |
| gpt-5.6-luna:xhigh | $0.14         | 49                 |
| gpt-5.6-luna:max   | $0.21         | 51                 |
| gpt-5.6-sol:medium | $0.31         | 54                 |
| gpt-5.6-sol:high   | $0.45         | 56                 |
| gpt-5.6-sol:xhigh  | $0.68         | 58                 |
| gpt-5.6-sol:max    | $1.04         | 59                 |

## Intelligence vs. Time per Intelligence Index Task

Artificial Analysis Intelligence Index · Weighted average decode time (minutes) per task; excludes TTFT and overhead time

### Time per Intelligence Index Task

The weighted average time (seconds) per Artificial Analysis Intelligence Index task. This is calculated by dividing output tokens per task by output speed, weighted by the relative weights of each benchmark in the Intelligence Index.

### Artificial Analysis Intelligence Index

Artificial Analysis Intelligence Index v4.1 includes: GDPval-AA v2, 𝜏³-Banking, Terminal-Bench v2.1, SciCode, Humanity's Last Exam, GPQA Diamond, CritPt, AA-Omniscience, AA-LCR. See Intelligence Index methodology for further details, including a breakdown of each evaluation and how we run them.

### Data Table

| Model              | Time Per Task | Intelligence Index |
| ------------------ | ------------- | ------------------ |
| gpt-5.6-luna:high  | 0.7min        | 46                 |
| gpt-5.6-luna:xhigh | 1.1min        | 49                 |
| gpt-5.6-luna:max   | 1.4min        | 51                 |
| gpt-5.6-sol:medium | 1.3min        | 54                 |
| gpt-5.6-sol:high   | 2.0min        | 56                 |
| gpt-5.6-sol:xhigh  | 2.7min        | 58                 |
| gpt-5.6-sol:max    | 4.1min        | 59                 |

## Intelligence vs. Output Speed

Artificial Analysis Intelligence Index · Output speed: output tokens per second

### Intelligence vs. Speed Trade-off

There is a trade-off between model quality and output speed, with higher intelligence models typically having lower output speed.

### Artificial Analysis Intelligence Index

Artificial Analysis Intelligence Index v4.1 includes: GDPval-AA v2, 𝜏³-Banking, Terminal-Bench v2.1, SciCode, Humanity's Last Exam, GPQA Diamond, CritPt, AA-Omniscience, AA-LCR. See Intelligence Index methodology for further details, including a breakdown of each evaluation and how we run them.

### Output Speed

Tokens per second received while the model is generating tokens (ie. after first chunk has been received from the API for models which support streaming).

### Model Performance Representation

Figures represent performance of the model's first-party API (e.g. OpenAI for o1) or the median across providers where a first-party API is not available (e.g. Meta's Llama models).

### Data Table

| Model              | Output Speed (tokens/sec) | Intelligence Index |
| ------------------ | ------------------------- | ------------------ |
| gpt-5.6-luna:high  | 184.154                   | 46                 |
| gpt-5.6-luna:xhigh | 195.192                   | 49                 |
| gpt-5.6-luna:max   | 220.876                   | 51                 |
| gpt-5.6-sol:medium | 54.262                    | 54                 |
| gpt-5.6-sol:high   | 55.5193                   | 56                 |
| gpt-5.6-sol:xhigh  | 60.8014                   | 58                 |
| gpt-5.6-sol:max    | 57.3194                   | 59                 |

## Intelligence vs. End-to-End Response Time

Artificial Analysis Intelligence Index · Seconds to output 500 tokens, including reasoning model 'thinking' time · Lower is better

### Artificial Analysis Intelligence Index

Artificial Analysis Intelligence Index v4.1 includes: GDPval-AA v2, 𝜏³-Banking, Terminal-Bench v2.1, SciCode, Humanity's Last Exam, GPQA Diamond, CritPt, AA-Omniscience, AA-LCR. See Intelligence Index methodology for further details, including a breakdown of each evaluation and how we run them.

### End-to-End Response Time

Seconds to receive a 500 token response. Key components:

- Input time: Time to receive the first response token
- Thinking time (only for reasoning models): Time reasoning models spend outputting tokens to reason prior to providing an answer. Amount of tokens based on the average reasoning tokens across a diverse set of 60 prompts (methodology details).
- Answer time: Time to generate 500 output tokens, based on output speed

### Model Performance Representation

Figures represent performance of the model's first-party API (e.g. OpenAI for o1) or the median across providers where a first-party API is not available (e.g. Meta's Llama models).

### Data Table

| Model              | End-to-End Response Time | Intelligence Index |
| ------------------ | ------------------------ | ------------------ |
| gpt-5.6-luna:high  | 7.8s                     | 46                 |
| gpt-5.6-luna:xhigh | 33s                      | 49                 |
| gpt-5.6-luna:max   | 115.9s                   | 51                 |
| gpt-5.6-sol:medium | 14s                      | 54                 |
| gpt-5.6-sol:high   | 23s                      | 56                 |
| gpt-5.6-sol:xhigh  | 46.1s                    | 58                 |
| gpt-5.6-sol:max    | 153.7s                   | 59                 |
