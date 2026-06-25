# Neovim + Zellij setup

Recommended configuration for working on this repo. Assumes a recent Neovim (0.10+) and `lazy.nvim` plugin manager.

## LSPs / formatters / linters needed

| File type | LSP | Formatter | Linter |
|---|---|---|---|
| Python (Pulumi, Lambda) | `pyright` or `basedpyright` | `ruff format` | `ruff check` |
| YAML (K8s, Argo, Helm values) | `yamlls` | `prettier` | `yamllint` |
| Helm templates | `helm_ls` | — | `helm lint` |
| Markdown (docs) | `marksman` | `prettier` | — |
| Bash (scripts) | `bashls` | `shfmt` | `shellcheck` |
| JSON | `jsonls` | `prettier` | — |
| Dockerfile (none here, but useful generally) | `dockerls` | — | `hadolint` |

## Lazy.nvim spec

Drop this into `~/.config/nvim/lua/plugins/devops.lua`:

```lua
return {
  -- Mason: tool installer
  {
    "williamboman/mason.nvim",
    opts = {
      ensure_installed = {
        "pyright",
        "ruff",
        "yaml-language-server",
        "helm-ls",
        "marksman",
        "bash-language-server",
        "json-lsp",
        "shfmt",
        "shellcheck",
        "yamllint",
        "prettier",
      },
    },
  },

  -- LSP configs
  {
    "neovim/nvim-lspconfig",
    opts = function(_, opts)
      local lsp = require("lspconfig")

      lsp.pyright.setup({
        settings = {
          python = {
            analysis = {
              typeCheckingMode = "standard",
              autoSearchPaths = true,
              useLibraryCodeForTypes = true,
            },
          },
        },
      })

      lsp.ruff.setup({})

      lsp.yamlls.setup({
        settings = {
          yaml = {
            schemas = {
              kubernetes = "apps/**/*.yaml",
              ["https://raw.githubusercontent.com/argoproj/argo-cd/master/manifests/crds/application-crd.yaml"] = "argocd/apps/*.yaml",
              ["https://json.schemastore.org/github-workflow.json"] = ".github/workflows/*.yaml",
            },
            schemaStore = { enable = true, url = "https://www.schemastore.org/api/json/catalog.json" },
            format = { enable = true },
            validate = true,
            completion = true,
          },
        },
      })

      lsp.helm_ls.setup({
        settings = {
          ["helm-ls"] = {
            yamlls = { path = "yaml-language-server" },
          },
        },
        filetypes = { "helm" },
      })

      lsp.bashls.setup({})
      lsp.marksman.setup({})
      lsp.jsonls.setup({})
    end,
  },

  -- Filetype detection for Helm templates
  {
    "towolf/vim-helm",
    ft = "helm",
  },

  -- Formatter dispatcher
  {
    "stevearc/conform.nvim",
    opts = {
      formatters_by_ft = {
        python = { "ruff_format" },
        yaml = { "prettier" },
        json = { "prettier" },
        markdown = { "prettier" },
        sh = { "shfmt" },
      },
      format_on_save = { timeout_ms = 2000, lsp_fallback = true },
    },
  },

  -- Linter dispatcher
  {
    "mfussenegger/nvim-lint",
    opts = {
      linters_by_ft = {
        sh = { "shellcheck" },
        yaml = { "yamllint" },
      },
    },
    config = function(_, opts)
      require("lint").linters_by_ft = opts.linters_by_ft
      vim.api.nvim_create_autocmd({ "BufWritePost", "BufReadPost" }, {
        callback = function() require("lint").try_lint() end,
      })
    end,
  },

  -- Treesitter parsers
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
      opts.ensure_installed = vim.list_extend(opts.ensure_installed or {}, {
        "python", "yaml", "helm", "bash", "markdown", "markdown_inline",
        "json", "dockerfile", "hcl", "go",
      })
    end,
  },

  -- Telescope file picker (most useful here)
  -- + a custom command to jump straight to common files
  {
    "nvim-telescope/telescope.nvim",
    keys = {
      { "<leader>fp", function() require("telescope.builtin").find_files({ cwd = "pulumi" }) end, desc = "Find: Pulumi" },
      { "<leader>fa", function() require("telescope.builtin").find_files({ cwd = "apps" }) end, desc = "Find: Apps" },
      { "<leader>fk", function() require("telescope.builtin").find_files({ cwd = "argocd" }) end, desc = "Find: Argo CD" },
    },
  },
}
```

## kubectl integration

`kubectl.nvim` is a clean way to interact with the cluster without leaving Neovim:

```lua
{
  "Ramilito/kubectl.nvim",
  cmd = "Kubectl",
  keys = {
    { "<leader>k", "<cmd>Kubectl<cr>", desc = "Open kubectl panel" },
  },
}
```

## Zellij layout

Create `~/.config/zellij/layouts/valheim.kdl`:

```kdl
layout {
    pane size=1 borderless=true {
        plugin location="zellij:tab-bar"
    }

    pane split_direction="vertical" {
        pane size="60%" {
            command "nvim"
            args "."
        }
        pane split_direction="horizontal" {
            pane size="50%" {
                name "kubectl"
                command "watch"
                args "-n" "2" "kubectl get pods -A"
            }
            pane {
                name "logs"
                command "bash"
            }
        }
    }

    pane size=2 borderless=true {
        plugin location="zellij:status-bar"
    }
}
```

Launch with:

```bash
zellij --layout ~/.config/zellij/layouts/valheim.kdl
```

Top-left: Neovim. Top-right: live pod status. Bottom-right: scratch shell for `just` commands, `kubectl logs`, `talosctl dashboard`, etc.

## Yank kubeconfig context into Neovim's :term

If you'd rather not maintain multiple panes, run `:terminal` inside Neovim and source the project's `.envrc`:

```vim
:terminal
:! source .envrc && kubectl get pods -A
```

Or bind it:

```lua
vim.keymap.set("n", "<leader>tt", function()
  vim.cmd("split | terminal")
  vim.cmd("startinsert")
end)
```

## Optional: pulumi-lsp

There is no official Pulumi LSP, but `pyright` already understands Pulumi's Python SDK perfectly. Don't waste time looking for a "Pulumi LSP."

## Optional: tflint-equivalent for Pulumi

Pulumi has no built-in linter. The closest is `pulumi preview` itself — it'll catch type errors and missing resources. For style, `ruff` handles everything.
