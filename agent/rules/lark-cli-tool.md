# Lark CLI execution

When any `lark-*` skill needs to run `lark-cli`, call the `lark_cli` custom tool.

- Pass argv tokens in `args` without the `lark-cli` executable or shell quoting.
- Never invoke `lark-cli` through Bash, Eval, Task, or a generated script.
- Keep the fixed `omp-user` profile and user identity.
- Read commands are eligible for automatic approval. Write commands require approval. High-risk writes remain blocked by the CLI policy.
