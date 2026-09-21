---
id: "textbook-ch15-s05"
corpus: "textbook"
slug: "ch15-05-soa-design-requirements"
title: "SOA设计的标准要求"
kind: "section"
order: 5
parent: "textbook-ch15"
source_pages: "525-526"
---

# 15.5 SOA设计的标准要求

## 15.5.1 文档标准化

SOA服务具有平台独立的自我描述XML文档。Web服务描述语言是用于描述服务的标准语言。

## 15.5.2 通信协议标准

SOA服务用消息进行通信，该消息通常使用XML Schema来定义(也称作XSD,XML Schema Definition)。消费者和提供者，或消费者和服务之间的通信多见于不知道提供者的环境中。服务间的通信也可以看作企业内部处理的关键商业文档。

## 15.5.3 应用程序统一登记与集成

在一个企业内部，SOA服务通过一个扮演目录列表 (Directory Listing) 角色的登记处(Registry) 来进行维护。应用程序在登记处 (Registry) 寻找并调用某项服务。统一描述、定义和集成是服务登记的标准。

## 15.5.4 服务质量 (QoS)

每项SOA服务都有一个与之相关的服务质量 (Quality of Service,QoS)。QoS的一些关键元素有安全需求(例如认证和授权)、可靠通信以及谁能调用服务的策略。

在企业中，关键任务系统用来解决高级需求，例如安全性、可靠性和事务。当一个企业开始采用服务架构作为工具来进行开发和部署应用的时候，基本的Web服务规范，像WSDL、SOAP以及UDDI就不能满足这些高级需求。正如前面所提到的，这些需求也称作服务质量。

与QoS相关的众多规范已经由一些标准化组织 (Standards Bodies) 提出，像W3C和OASIS(the Organization for the Advancement of Structured Information Standards)。下面的部分将会讨论一些QoS服务和相关标准。

### 1. 可靠性

在典型的SOA环境中，服务消费者和服务提供者之间会有几种不同的文档在进行交换。

具有诸如“仅且仅仅传送一次 (Once-and-only-once Delivery)”“最多传送一次 (At-most-once Delivery)”“重复消息过滤 (Duplicate Message Elimination)” 和“保证消息传送 (Guaranteed Message Delivery)”等特性消息的发送和确认，在关键任务系统 (Mission-critical Systems) 中变得十分重要。WS-Reliability和WS-Reliable Messaging是两个用来解决此类问题的标准。这些标准现在都由OASIS负责。

### 2. 安全性

Web服务安全规范用来保证消息的安全性。该规范主要包括认证交换、消息完整性和消息保密。该规范吸引人的地方在于它借助现有的安全标准，例如，SAML (Security Assertion Markup Language) 实现Web服务消息的安全。OASIS正致力于Web服务安全规范的制定。

### 3. 策略

服务提供者有时候会要求服务消费者与某种策略通信。例如，服务提供商可能会要求消费者提供Kerberos安全标识才能取得某项服务。这些要求被定义为策略断言 (Policy Assertions),一项策略可能会包含多个断言。WS-Policy用来标准化服务消费者和服务提供者之间的策略通信。

### 4. 控制

在SOA中，进程是使用一组离散的服务创建的。BPEL4WS或者WSBPEL(Web Service Business Process Execution Language) 是用来控制这些服务的语言。当企业着手于服务架构时，服务可以用来整合数据仓库 (Silos of Data), 应用程序，以及组件。整合应用意味着像异步通信，并行处理，数据转换，以及校正等进程请求必须被标准化。

### 5. 管理

随着企业服务的增长，所使用的服务和业务进程数量也随之增加，一个让系统管理员管理所有运行在多种环境下的服务的系统就显得尤为重要。WSDM (Web Services for Distributed Management) 的制定，使任何根据WSDM实现的服务都可以由一个兼容WSDM (WSDM-compliant) 的管理方案来管理。

其他的QoS特性，例如合作方之间的沟通和通信，多个服务之间的事务处理，都在WS-Coordination和WS-Transaction标准中描述，这些都是OASIS的工作。
