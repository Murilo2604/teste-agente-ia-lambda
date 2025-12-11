# GCB AI Agent - Arquitetura da Infraestrutura

## Diagrama de Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              MÓDULO RAIZ TERRAFORM                                   │
│                         (environments/dev ou prod)                                   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           DATA SOURCES                                       │   │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐ │   │
│  │  │ aws_caller_      │ │ aws_region       │ │ aws_s3_bucket                │ │   │
│  │  │ identity         │ │                  │ │ (bucket existente)           │ │   │
│  │  │ → account_id     │ │ → region_name    │ │ → bucket_arn                 │ │   │
│  │  └──────────────────┘ └──────────────────┘ └──────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────────────┐
│    MÓDULO ECR       │   │    MÓDULO SQS       │   │        BUCKET S3            │
│   (independente)    │   │   (independente)    │   │       (existente)           │
├─────────────────────┤   ├─────────────────────┤   ├─────────────────────────────┤
│ Recursos:           │   │ Recursos:           │   │ Referenciado via data       │
│ • aws_ecr_          │   │ • aws_sqs_queue     │   │ source para políticas IAM   │
│   repository        │   │   (FIFO principal)  │   │                             │
│ • aws_ecr_          │   │ • aws_sqs_queue     │   │ Armazena:                   │
│   lifecycle_policy  │   │   (FIFO DLQ)        │   │ • PDFs de entrada           │
│ • aws_ecr_          │   │ • aws_sqs_queue_    │   │ • Resultados processados    │
│   repository_policy │   │   policy            │   │ • Recortes/artefatos        │
├─────────────────────┤   │ • aws_ssm_parameter │   └─────────────────────────────┘
│ Outputs:            │   │   (queue_url)       │                 │
│ • repository_url    │   │ • aws_ssm_parameter │                 │
│ • image_uri ────────┼───│   (dlq_url)         │                 │
│ • repository_arn    │   ├─────────────────────┤                 │
└─────────────────────┘   │ Outputs:            │                 │
          │               │ • queue_arn ────────┼─────────┐       │
          │               │ • queue_url ────────┼─────────┼───┐   │
          │               │ • dlq_arn           │         │   │   │
          │               │ • dlq_url           │         │   │   │
          │               └─────────────────────┘         │   │   │
          │                             │                 │   │   │
          │                             │                 │   │   │
          │                             ▼                 ▼   │   │
          │               ┌─────────────────────────────────┐ │   │
          │               │         MÓDULO IAM              │ │   │
          │               │   (depende de: SQS, S3)         │ │   │
          │               ├─────────────────────────────────┤ │   │
          │               │ Inputs:                         │ │   │
          │               │ • sqs_queue_arn ◄───────────────┘ │   │
          │               │ • s3_bucket_arn ◄─────────────────┼───┘
          │               ├─────────────────────────────────┤ │
          │               │ Recursos:                       │ │
          │               │ • aws_iam_role                  │ │
          │               │   (lambda_execution_role)       │ │
          │               │ • aws_iam_role_policy_          │ │
          │               │   attachment (CloudWatch)       │ │
          │               │ • aws_iam_role_policy_          │ │
          │               │   attachment (ECR ReadOnly)     │ │
          │               │ • aws_iam_role_policy           │ │
          │               │   (acesso SQS)                  │ │
          │               │ • aws_iam_role_policy           │ │
          │               │   (acesso S3)                   │ │
          │               ├─────────────────────────────────┤ │
          │               │ Outputs:                        │ │
          │               │ • lambda_execution_role_arn ────┼─┼───┐
          │               │ • lambda_execution_role_name    │ │   │
          │               └─────────────────────────────────┘ │   │
          │                                                   │   │
          │                                                   │   │
          ▼                                                   ▼   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              MÓDULO LAMBDA                                           │
│                    (depende de: ECR, IAM, SQS)                                       │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Inputs:                                                                              │
│ • ecr_image_uri ◄──────── (do módulo ECR)                                           │
│ • lambda_role_arn ◄────── (do módulo IAM)                                           │
│ • sqs_queue_arn ◄──────── (do módulo SQS) - para event source mapping               │
│ • sqs_queue_url ◄──────── (do módulo SQS) - para variável de ambiente               │
│ • s3_bucket_name ◄─────── (das variáveis)                                           │
│ • openai_api_key ◄─────── (das variáveis - sensível)                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Recursos:                                                                            │
│ • aws_lambda_function (imagem container do ECR)                                     │
│   - Variáveis de ambiente: OPENAI_API_KEY, S3_BUCKET_NAME, SQS_QUEUE_URL            │
│ • aws_lambda_event_source_mapping (SQS → Lambda trigger)                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Outputs:                                                                             │
│ • function_arn, function_name, invoke_arn, event_source_mapping_uuid                │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Diagrama de Fluxo de Dados

```
┌──────────────────┐
│   PIPELINE CI/CD │
│  (GitHub Actions │
│   ou similar)    │
└────────┬─────────┘
         │
         │ 1. docker build & push
         ▼
┌──────────────────┐
│  REPOSITÓRIO ECR │
│  gcb-ai-agent-   │
│  {env}:latest    │
└────────┬─────────┘
         │
         │ 2. Lambda baixa a imagem
         │    (no cold start)
         ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   SISTEMA        │     │   FILA SQS       │     │     FUNÇÃO       │
│   EXTERNO        │────▶│   FIFO           │────▶│     LAMBDA       │
│   (envia job)    │     │                  │     │                  │
└──────────────────┘     │  gcb-ai-agent-   │     │  gcb-ai-agent-   │
                         │  queue-{env}     │     │  lambda-{env}    │
                         │  .fifo           │     │                  │
                         └────────┬─────────┘     └────────┬─────────┘
                                  │                        │
                                  │ Falha após             │ 3. Processa PDF
                                  │ max_receive_count      │
                                  ▼                        ▼
                         ┌──────────────────┐     ┌──────────────────┐
                         │   FILA DLQ       │     │   BUCKET S3      │
                         │                  │     │                  │
                         │  gcb-ai-agent-   │     │  • Download PDF  │
                         │  dlq-{env}.fifo  │     │  • Upload result │
                         └──────────────────┘     │  • Armazenar     │
                                                  │    recortes      │
                                                  └────────┬─────────┘
                                                           │
                                                           │ 4. Chama endpoint
                                                           │    externo
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ API EXTERNA      │
                                                  │ (callback de     │
                                                  │  notificação)    │
                                                  └──────────────────┘
```

---

## Grafo de Dependências dos Módulos

```
                    ┌─────────────────┐
                    │    VARIÁVEIS    │
                    │   (tfvars)      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  MÓDULO ECR   │   │  MÓDULO SQS   │   │  DATA SOURCE  │
│ (independente)│   │ (independente)│   │  aws_s3_bucket│
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        │           ┌───────┴───────────────────┘
        │           │
        │           ▼
        │   ┌───────────────┐
        │   │  MÓDULO IAM   │
        │   │ (precisa: SQS │
        │   │  ARN, S3 ARN) │
        │   └───────┬───────┘
        │           │
        └─────┬─────┘
              │
              ▼
      ┌───────────────┐
      │ MÓDULO LAMBDA │
      │ (precisa: ECR │
      │  image_uri,   │
      │  IAM role_arn,│
      │  SQS arn/url) │
      └───────────────┘
```

---

## Resumo de Recursos por Módulo

| Módulo | Recursos Criados | Outputs Usados Por |
|--------|------------------|-------------------|
| **ECR** | `aws_ecr_repository`, `aws_ecr_lifecycle_policy`, `aws_ecr_repository_policy` | Lambda (image_uri) |
| **SQS** | `aws_sqs_queue` (principal), `aws_sqs_queue` (DLQ), `aws_sqs_queue_policy`, `aws_ssm_parameter` x2 | IAM (queue_arn), Lambda (queue_arn, queue_url) |
| **IAM** | `aws_iam_role`, `aws_iam_role_policy_attachment` x2, `aws_iam_role_policy` x2 | Lambda (role_arn) |
| **Lambda** | `aws_lambda_function`, `aws_lambda_event_source_mapping` | Outputs do root |

---

## Matriz de Permissões IAM

| Permissão | Recurso | Propósito |
|-----------|---------|-----------|
| `AWSLambdaBasicExecutionRole` | CloudWatch Logs | Logging da Lambda |
| `AmazonEC2ContainerRegistryReadOnly` | ECR | Baixar imagens de container |
| `sqs:ReceiveMessage, DeleteMessage, GetQueueAttributes, GetQueueUrl` | Fila SQS | Processar mensagens |
| `s3:GetObject, PutObject, PutObjectAcl` | Bucket S3/* | Ler/escrever arquivos |
| `s3:ListBucket` | Bucket S3 | Listar conteúdo do bucket |

---

## Variáveis de Ambiente (Lambda)

| Variável | Origem | Descrição |
|----------|--------|-----------|
| `OPENAI_API_KEY` | tfvars (sensível) | Chave de API da OpenAI |
| `S3_BUCKET_NAME` | tfvars | Bucket S3 de destino |
| `S3_ENDPOINT` | tfvars | URL do endpoint S3 |
| `SQS_QUEUE_URL` | Output do módulo SQS | URL da fila para polling |
| `PYTHONUNBUFFERED` | hardcoded | Buffering de output Python |

---

## Estrutura de Arquivos

```
infra/
├── modules/
│   ├── ecr/                    # Cria repositório ECR (CI/CD faz push das imagens)
│   │   ├── main.tf             # Repositório, lifecycle policy, repository policy
│   │   ├── variables.tf        # name_prefix, environment, image_tag
│   │   ├── outputs.tf          # repository_url, image_uri, repository_arn
│   │   └── README.md           # Documentação do módulo
│   │
│   ├── iam/                    # Cria role de execução Lambda e políticas
│   │   ├── main.tf             # Role, policy attachments, inline policies
│   │   ├── variables.tf        # name_prefix, environment, sqs_queue_arn, s3_bucket_arn
│   │   └── outputs.tf          # lambda_execution_role_arn, role_name
│   │
│   ├── lambda/                 # Cria função Lambda com trigger SQS
│   │   ├── main.tf             # Lambda function, event source mapping
│   │   ├── variables.tf        # Todas as configurações da Lambda
│   │   └── outputs.tf          # function_arn, function_name
│   │
│   └── sqs/                    # Cria filas FIFO com DLQ
│       ├── main.tf             # Filas, políticas, parâmetros SSM
│       ├── variables.tf        # name_prefix, environment, configurações da fila
│       └── outputs.tf          # queue_arn, queue_url, dlq_arn, dlq_url
│
└── environments/
    ├── dev/                    # Ambiente de desenvolvimento
    │   ├── main.tf             # Orquestra todos os módulos
    │   ├── variables.tf        # Variáveis do ambiente
    │   ├── outputs.tf          # Todos os outputs + helpers CI/CD
    │   └── dev.tfvars          # Valores específicos do dev
    │
    └── prod/                   # Ambiente de produção
        ├── main.tf             # Orquestra todos os módulos
        ├── variables.tf        # Variáveis do ambiente
        ├── outputs.tf          # Todos os outputs + helpers CI/CD
        └── prod.tfvars         # Valores específicos do prod
```

---

## Integração com CI/CD

### Responsabilidades do Terraform
- Criar repositório ECR
- Criar função Lambda com referência inicial à imagem
- Gerenciar toda a infraestrutura (IAM, SQS, políticas S3)
- Exportar URL do repositório ECR para uso do CI/CD

### Responsabilidades do Pipeline CI/CD
- Build da imagem Docker a partir do código da aplicação
- Autenticar no ECR (`aws ecr get-login-password`)
- Taggear imagem com versão/commit SHA/latest
- Push da imagem para o repositório ECR
- Atualizar código da Lambda: `aws lambda update-function-code`
- Aguardar atualização: `aws lambda wait function-updated`

### Fluxo de Trabalho

1. **Setup Inicial**: Execute Terraform para criar infraestrutura (repositório ECR existe mas está vazio)
2. **Primeiro Deploy**: CI/CD faz push da imagem inicial, Terraform apply cria Lambda apontando para ela
3. **Deploys Subsequentes**: CI/CD faz push de novas imagens e atualiza código da Lambda
4. **Mudanças de Infraestrutura**: Execute Terraform apply (não afeta imagens deployadas)

---

## Pontos Fortes da Arquitetura

1. **Separação clara de módulos** - Cada módulo tem uma responsabilidade única
2. **Nomenclatura dinâmica** - Todos os recursos usam padrão `${name_prefix}-${environment}`
3. **Sem valores hardcoded** - Toda configuração via variáveis
4. **Data sources** - Account ID e região descobertos dinamicamente
5. **CI/CD friendly** - Outputs do ECR fornecem comandos docker
6. **Cadeia de dependências correta** - `depends_on` garante ordem de criação correta

---

## Notas da Arquitetura

1. **Bucket S3 é externo** - Referenciado via data source, não criado pelo Terraform
2. **Imagens ECR via CI/CD** - Terraform cria repositório, CI/CD faz push das imagens
3. **Parâmetros SSM** - URLs das filas armazenadas para descoberta externa
4. **Filas FIFO** - Garantem processamento ordenado com deduplicação
5. **DLQ configurada** - Mensagens falhas após `max_receive_count` vão para fila de dead-letter

---

## Comandos Úteis

### Inicializar Terraform
```bash
cd infra/environments/dev
terraform init
```

### Planejar mudanças
```bash
terraform plan -var-file=dev.tfvars
```

### Aplicar mudanças
```bash
terraform apply -var-file=dev.tfvars
```

### Ver outputs
```bash
terraform output
```

### Comandos Docker (do output do Terraform)
```bash
# Login no ECR
$(terraform output -raw docker_login_command)

# Build, tag e push
terraform output docker_build_and_push_commands
```

---

## Variáveis Sensíveis

A variável `openai_api_key` deve ser fornecida via:

1. **Variável de ambiente**: `export TF_VAR_openai_api_key="sk-..."`
2. **Arquivo tfvars** (não commitar): Adicionar ao `.gitignore`
3. **Secret manager**: Integrar com AWS Secrets Manager ou similar

---

*Última atualização: Dezembro 2024*

