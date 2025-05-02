# 启用GitHub Actions Docker镜像发布

要使GitHub Actions能够成功构建并发布Docker镜像到GitHub Container Registry (ghcr.io)，需要进行以下设置：

## 1. 设置仓库权限

1. 打开你的GitHub仓库页面
2. 点击 **Settings** （设置）标签
3. 在左侧菜单栏中，点击 **Actions** > **General**
4. 在 **Workflow permissions** 部分，选择 **Read and write permissions**
5. 点击 **Save** 保存更改

## 2. 配置包访问权限

1. 点击仓库的 **Settings** 标签
2. 在左侧菜单栏中，点击 **Packages**
3. 确保 **Inherit access from source repository** 选项已启用
4. 如需更精细的访问控制，可以在此页面进行其他设置

## 3. 设置分支保护（可选但推荐）

1. 点击仓库的 **Settings** 标签
2. 在左侧菜单栏中，点击 **Branches**
3. 在 **Branch protection rules** 部分，点击 **Add rule**
4. 在 **Branch name pattern** 中输入 `main` 或 `master`
5. 配置适合的分支保护规则，然后点击 **Create**/**Save**

## 4. 访问构建的Docker镜像

GitHub Actions成功运行后，Docker镜像将被发布到GitHub Container Registry。你可以通过以下方式访问：

1. 访问你的GitHub个人资料或组织页面
2. 点击 **Packages** 标签
3. 找到 `okx-grid-bot` 包
4. 使用如下命令拉取镜像：

```bash
docker pull ghcr.io/用户名/okx-grid-bot:latest
```

## 5. 排错

如果GitHub Actions工作流失败，请检查：

1. 工作流日志中的错误信息
2. 确认已正确设置仓库权限
3. 检查Dockerfile是否有问题
4. 确保工作流YAML文件(.github/workflows/docker-build.yml)格式正确

## 6. 注意事项

- GitHub提供的GITHUB_TOKEN默认具有推送包的权限，因此通常不需要额外的身份验证
- 私有仓库发布的镜像默认也是私有的，需要身份验证才能拉取
- 公开仓库发布的镜像默认是公开的，可以无需身份验证拉取 