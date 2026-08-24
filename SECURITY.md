# 安全与私下联系渠道

本仓库是一个知识库，不是可部署的软件，因此“安全问题”主要有两类：仓库自有脚本
（`scripts/`、`.github/workflows/`）的缺陷，以及**需要私下沟通的内容权利问题**。
两类都走下面同一个私密入口。

## 私密上报入口

请使用 GitHub 的 **Private vulnerability reporting**（私密漏洞上报）：

1. 打开仓库的 [Security 页面](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/security)；
2. 点击 **Report a vulnerability**；
3. 填写内容后提交。

该会话只有你和仓库维护者可见，不会公开索引，也不会出现在 Issue 列表里。它是本仓库
**唯一的私密书面渠道**——请不要把敏感材料贴进公开 Issue。

> 若该按钮不可见，说明维护者尚未启用此功能，请在仓库 Settings → Advanced Security →
> Private vulnerability reporting 中开启（仓库管理员操作，无需公开任何邮箱地址）。

## 适用场景

**脚本缺陷。** 如果发现校验/审计脚本存在会破坏他人本地环境、泄露本地路径或凭据、
或可被输入内容操纵的问题，请私下上报，不要先公开 PoC。这些脚本只读取仓库内文件、
不联网、不写入正文，因此攻击面很小；但报告仍然欢迎。

**内容权利问题。** 权利人或其授权代表如需提交身份证明、授权文件、合同等敏感材料，
请用上面的私密渠道，而不是公开 Issue。公开的下架请求模板见
[版权/下架请求](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/issues/new?template=rights-request.yml)，
完整流程见 [CONTENT_POLICY.md](CONTENT_POLICY.md) 第 6 节。

**不属于本渠道的问题。** OCR 错字、题面缺失、答案争议等内容勘误请走公开的
[内容勘误](https://github.com/YoungHong1992/ruankao-senior-architecture-designer/issues/new?template=correction.yml)
模板——它们需要公开的可复核证据，公开讨论对所有使用者都有价值。

## 响应说明

本项目由个人在业余时间维护，无服务等级承诺（SLA），也不提供漏洞赏金。维护者会在
力所能及的范围内尽快回应；涉及内容权利的请求可在核验期间先行限制或移除有争议内容。

本文件不构成法律意见。
