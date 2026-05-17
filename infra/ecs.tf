resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.project}-cluster" }
}

resource "aws_cloudwatch_log_group" "fastapi" {
  name              = "/ecs/${var.project}/fastapi"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "fastapi" {
  family                   = "${var.project}-fastapi"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fastapi_cpu
  memory                   = var.fastapi_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "fastapi"
    image = "${aws_ecr_repository.fastapi.repository_url}:v2"
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "ENVIRONMENT", value = var.environment },
      { name = "POSTGRES_HOST", value = aws_db_instance.postgres.address },
      { name = "POSTGRES_PORT", value = "5432" },
      { name = "POSTGRES_DB", value = var.db_name },
      { name = "POSTGRES_USER", value = var.db_username },
      { name = "REDIS_HOST", value = aws_elasticache_cluster.redis.cache_nodes[0].address },
      { name = "REDIS_PORT", value = "6379" },
      # GPU instance address — use private IP (EIP hairpin doesn't work within VPC)
      { name = "OLLAMA_HOST", value = "10.0.1.7" },
      { name = "OLLAMA_PORT", value = "11434" },
      { name = "QDRANT_HOST", value = "10.0.1.7" },
      { name = "QDRANT_PORT", value = "6333" },
      # Models
      { name = "PRIMARY_MODEL", value = "scb10x/llama3.1-typhoon2-8b-instruct" },
      { name = "EMBEDDING_MODEL", value = "nomic-embed-text" },
      { name = "FALLBACK_MODEL", value = "gemma2:9b" },
      { name = "SAFETY_MODEL", value = "llama-guard3:1b" },
      # RAG
      { name = "TOP_K_RETRIEVAL", value = "5" },
      { name = "RERANKER_TOP_K", value = "3" },
      # Rate limits
      { name = "CHAT_RATE_LIMIT_PER_HOUR", value = "60" },
      { name = "INGESTION_RATE_LIMIT_PER_HOUR", value = "10" },
    ]

    secrets = [
      {
        name      = "POSTGRES_PASSWORD"
        valueFrom = aws_secretsmanager_secret.db_password.arn
      },
      {
        name      = "FIREBASE_CREDENTIALS_JSON"
        valueFrom = aws_secretsmanager_secret.firebase_credentials.arn
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.fastapi.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "fastapi"
        "awslogs-create-group"  = "true"
      }
    }

  }])
}

resource "aws_ecs_service" "fastapi" {
  name            = "${var.project}-fastapi"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.fastapi.arn
  desired_count   = var.fastapi_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.fastapi.arn
    container_name   = "fastapi"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    # Allow external CI/CD deploys to update the task definition without Terraform drift
    ignore_changes = [task_definition]
  }
}
