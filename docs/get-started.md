---
layout: default
title: Get started
standfirst: Three routes in, according to whether you wish to try the tools, apply them to your own handover, or read the specifications.
---

## Draft a contract in a browser

The Sentinel Contract Wizard requires no installation, no account and no
payment. It runs on a free Google Colab machine, and the language model it
uses runs on that machine, so the handover package supplied to it is not
transmitted to any third party service.

[Open the Sentinel Contract Wizard](https://colab.research.google.com/github/dbtl-synbio/dbtlhub/blob/main/contract-wizard/sentinel_contract_wizard.ipynb)

Two points before running it. A graphics card should be requested first,
through **Runtime**, then **Change runtime type**, then **T4 GPU**, then
**Save**, because without one the language model requires minutes rather
than seconds for each response. The first cell takes approximately 3
minutes, almost all of which is the download of the model.

The notebook will ask for a handover package and for a description of what
the receiving process requires. An example package is provided for anyone
who does not have one to hand.

## Check a handover against a contract

`sentinel-oo` may be run as a web service, which accepts a handover package
and returns it with the outcome of the check recorded inside it. Its
repository documents installation, the structure of a contract file, and
deployment.

[sentinel-oo]({{ site.repository_url }}/tree/main/sentinel-oo)

## Read the specifications

The contract files for each use case are held in the folder for that use
case within the project repository, together with example packages: one
which satisfies the contract and several which violate it in a single
respect each.

[Use cases]({{ '/use-cases.html' | relative_url }})
&middot;
[What a contract states]({{ '/contracts.html' | relative_url }})

## Contribute

The project is developed openly. Issues and contributions are welcome
through the repository, and the components are independent of one another,
so a contribution to one use case does not require familiarity with the
others.

[Project repository]({{ site.repository_url }})
