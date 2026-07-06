#python3 -m llama_cpp.server \
#  --model /storage/gguf/Qwen3-14B-Q4_K_M.gguf \
#  --host 127.0.0.1 \
#  --port 8080 \
#  --n_ctx 20960 \
#  --n_gpu_layers 25 \
#  --n_threads 40

python3 -m llama_cpp.server \
  --model /storage/gguf/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --n_ctx 13000 \
  --n_gpu_layers 13 \
  --n_threads 40

