# anysdk-mcp/SETUP.md

# MCP SDK Bridge Setup Guide

This guide will help you set up all the required API keys and credentials for the MCP SDK Bridge project.

## Quick Setup

1. Copy the environment template:
   ```bash
   cp env.template .env
   ```

2. Edit `.env` with your actual credentials (see detailed instructions below)

3. Make sure `.env` is in your `.gitignore`:
   ```bash
   echo ".env" >> .gitignore
   ```

## Detailed Setup Instructions

### 🐙 GitHub Setup

**What you need:** A GitHub Personal Access Token

**Steps:**
1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Give it a descriptive name like "MCP SDK Bridge"
4. Set expiration (recommended: 90 days or custom)
5. Select scopes based on what you need:
   - **`repo`** - Full repository access (for private repos)
   - **`public_repo`** - Public repository access (if only public repos)
   - **`user`** - User profile information
   - **`read:org`** - Read organization membership
   - **`issues`** - Create and manage issues
   - **`pull_requests`** - Create and manage pull requests
6. Click "Generate token"
7. **Copy the token immediately** (you won't see it again!)
8. Add to your `.env` file:
   ```
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

**Testing:**
```bash
# Test your token
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
```

### ☁️ Azure Setup

**What you need:** Azure subscription and service principal credentials

#### Option 1: Service Principal (Recommended for Production)

**Steps:**
1. **Get your Subscription ID:**
   - Go to [Azure Portal > Subscriptions](https://portal.azure.com/#view/Microsoft_Azure_Billing/SubscriptionsBlade)
   - Copy your Subscription ID

2. **Create a Service Principal:**
   - Go to [Azure Portal > Azure Active Directory > App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
   - Click "New registration"
   - Name: "MCP SDK Bridge"
   - Supported account types: "Accounts in this organizational directory only"
   - Click "Register"

3. **Get Application (Client) ID:**
   - In your new app registration, copy the "Application (client) ID"

4. **Get Tenant ID:**
   - In your app registration, copy the "Directory (tenant) ID"

5. **Create Client Secret:**
   - Go to "Certificates & secrets" tab
   - Click "New client secret"
   - Description: "MCP SDK Bridge Secret"
   - Expires: Choose appropriate duration
   - Click "Add"
   - **Copy the secret value immediately** (you won't see it again!)

6. **Assign Permissions:**
   - Go to [Azure Portal > Subscriptions](https://portal.azure.com/#view/Microsoft_Azure_Billing/SubscriptionsBlade)
   - Click your subscription
   - Go to "Access control (IAM)"
   - Click "Add" > "Add role assignment"
   - Role: "Contributor" (or more specific role as needed)
   - Assign access to: "User, group, or service principal"
   - Select your app registration
   - Click "Save"

7. **Add to your `.env` file:**
   ```
   AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   AZURE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

#### Option 2: Azure CLI (Recommended for Development)

**Steps:**
1. Install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
2. Login: `az login`
3. Set subscription: `az account set --subscription "Your Subscription Name"`
4. Get subscription ID: `az account show --query id -o tsv`
5. Add to your `.env` file:
   ```
   AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   # Leave client credentials empty to use CLI authentication
   ```

**Testing:**
```bash
# Test Azure CLI authentication
az account show

# Test service principal authentication
az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID
```

### ⚓ Kubernetes Setup

**What you need:** Access to a Kubernetes cluster

#### Option 1: Use Default Kubeconfig (Simplest)

If you already have `kubectl` configured:
1. Your kubeconfig is likely at `~/.kube/config`
2. No environment variables needed
3. The adapter will use your current context

#### Option 2: Custom Kubeconfig Location

**Steps:**
1. If your kubeconfig is in a different location:
   ```
   KUBECONFIG=/path/to/your/kubeconfig
   ```

#### Option 3: Specific Context

**Steps:**
1. List available contexts: `kubectl config get-contexts`
2. Set in `.env`:
   ```
   KUBE_CONTEXT=your-specific-context-name
   ```

#### Setting up a Kubernetes Cluster (if you don't have one)

**Local Development Options:**
- **minikube:** `brew install minikube && minikube start`
- **kind:** `brew install kind && kind create cluster`
- **Docker Desktop:** Enable Kubernetes in Docker Desktop settings

**Cloud Options:**
- **Azure AKS:** `az aks create` (requires Azure setup above)
- **Google GKE:** Use Google Cloud Console
- **AWS EKS:** Use AWS Console or CLI

**Testing:**
```bash
# Test Kubernetes connection
kubectl cluster-info
kubectl get nodes
```

## Environment File Setup

1. **Copy the template:**
   ```bash
   cp env.template .env
   ```

2. **Edit the `.env` file** with your actual values

3. **Secure your `.env` file:**
   ```bash
   # Make sure it's in .gitignore
   echo ".env" >> .gitignore
   
   # Set appropriate permissions
   chmod 600 .env
   ```

## Validation

Test your setup using the built-in validation:

```bash
# Validate GitHub setup
uv run python -m mcp_sdk_bridge.cli validate --sdk github

# Validate Azure setup
uv run python -m mcp_sdk_bridge.cli validate --sdk azure

# Validate Kubernetes setup
uv run python -m mcp_sdk_bridge.cli validate --sdk k8s

# List all available SDKs and their status
uv run python -m mcp_sdk_bridge.cli list
```

## Running the Bridge

Once everything is set up:

```bash
# Start GitHub MCP server
uv run python -m mcp_sdk_bridge.cli up --sdk github --validate

# Start Azure MCP server
uv run python -m mcp_sdk_bridge.cli up --sdk azure --validate

# Start Kubernetes MCP server
uv run python -m mcp_sdk_bridge.cli up --sdk k8s --validate
```

## Troubleshooting

### GitHub Issues
- **Invalid token:** Make sure token has correct permissions
- **Rate limiting:** GitHub has API rate limits, consider using a token with higher limits

### Azure Issues
- **Authentication failed:** Check service principal permissions
- **Subscription not found:** Verify subscription ID is correct
- **Permission denied:** Ensure service principal has appropriate role assignments

### Kubernetes Issues
- **Connection refused:** Check if cluster is running and accessible
- **Permission denied:** Verify your kubeconfig has appropriate permissions
- **Context not found:** Check available contexts with `kubectl config get-contexts`

### General Issues
- **Environment variables not loaded:** Make sure `.env` file is in the correct location
- **Import errors:** Run `uv sync` to install dependencies
- **Permission errors:** Check file permissions on config files

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use least privilege principle** - only grant necessary permissions
3. **Rotate credentials regularly**
4. **Use different credentials for development and production**
5. **Monitor API usage** for unexpected activity
6. **Use Azure Key Vault or similar** for production secrets management

## Next Steps

Once your environment is set up:
1. Read the main [README.md](README.md) for usage examples
2. Check out the [configuration files](configs/) for advanced settings
3. Run the test suite: `./test.sh`
4. Explore the available MCP tools for each SDK

