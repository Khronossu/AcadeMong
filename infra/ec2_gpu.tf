# EC2 GPU instance — runs Ollama (all LLM models) + Qdrant (vector DB)
# Both services start automatically via systemd units written in user_data.

# Deep Learning AMI with CUDA pre-installed (Ubuntu 22.04)
data "aws_ami" "deep_learning" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning OSS Nvidia Driver AMI GPU PyTorch * (Ubuntu 22.04)*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_instance" "gpu" {
  ami                    = data.aws_ami.deep_learning.id
  instance_type          = var.gpu_instance_type
  key_name               = var.gpu_key_name
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.gpu.id]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.gpu_volume_size_gb
    delete_on_termination = true
  }

  # Installs Ollama + Docker, pulls all required models, starts Qdrant in Docker.
  # Total cold-start time: ~10–15 min (model downloads).
  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -e

    # ── Ollama ────────────────────────────────────────────────────────────────
    curl -fsSL https://ollama.com/install.sh | sh

    # Bind Ollama to all interfaces so ECS tasks can reach it
    mkdir -p /etc/systemd/system/ollama.service.d
    cat > /etc/systemd/system/ollama.service.d/override.conf <<'UNIT'
    [Service]
    Environment="OLLAMA_HOST=0.0.0.0:11434"
    UNIT

    systemctl daemon-reload
    systemctl enable ollama
    systemctl start ollama

    # Wait for Ollama to be ready
    until curl -sf http://localhost:11434/api/tags > /dev/null; do sleep 2; done

    # Pull all required models (background to avoid blocking boot)
    nohup bash -c '
      ollama pull scb10x/llama3.1-typhoon2-8b-instruct
      ollama pull nomic-embed-text
      ollama pull gemma:8b
      ollama pull llama-guard3:1b
    ' >> /var/log/ollama-pull.log 2>&1 &

    # ── Docker (for Qdrant) ───────────────────────────────────────────────────
    apt-get update -y
    apt-get install -y docker.io
    systemctl enable docker
    systemctl start docker

    # Qdrant — persisted on the EBS root volume
    mkdir -p /data/qdrant
    docker run -d \
      --name qdrant \
      --restart always \
      -p 6333:6333 \
      -v /data/qdrant:/qdrant/storage \
      qdrant/qdrant

    echo "GPU instance bootstrap complete"
  EOF
  )

  tags = { Name = "${var.project}-gpu" }
}

# Elastic IP so the GPU instance address is stable across stop/start
resource "aws_eip" "gpu" {
  instance = aws_instance.gpu.id
  domain   = "vpc"

  tags = { Name = "${var.project}-gpu-eip" }
}
