## Navigation Menu

# Search code, repositories, users, issues, pull requests...

# Provide feedback

We read every piece of feedback, and take your input very seriously.

# Saved searches

## Use saved searches to filter your results more quickly

To see all available qualifiers, see our [documentation](https://docs.github.com/search-github/github-code-search/understanding-github-code-search-syntax).

# akfamily/akshare

## Folders and files

| Name | | Name | Last commit message | Last commit date |
| --- | --- | --- | --- | --- |
| Latest commit   History[838 Commits](/akfamily/akshare/commits/main/)   838 Commits | | |
| [.github](/akfamily/akshare/tree/main/.github ".github") | | [.github](/akfamily/akshare/tree/main/.github ".github") |  |  |
| [akshare](/akfamily/akshare/tree/main/akshare "akshare") | | [akshare](/akfamily/akshare/tree/main/akshare "akshare") |  |  |
| [assets/images](/akfamily/akshare/tree/main/assets/images "This path skips through empty directories") | | [assets/images](/akfamily/akshare/tree/main/assets/images "This path skips through empty directories") |  |  |
| [docs](/akfamily/akshare/tree/main/docs "docs") | | [docs](/akfamily/akshare/tree/main/docs "docs") |  |  |
| [tests](/akfamily/akshare/tree/main/tests "tests") | | [tests](/akfamily/akshare/tree/main/tests "tests") |  |  |
| [.gitignore](/akfamily/akshare/blob/main/.gitignore ".gitignore") | | [.gitignore](/akfamily/akshare/blob/main/.gitignore ".gitignore") |  |  |
| [.pre-commit-config.yaml](/akfamily/akshare/blob/main/.pre-commit-config.yaml ".pre-commit-config.yaml") | | [.pre-commit-config.yaml](/akfamily/akshare/blob/main/.pre-commit-config.yaml ".pre-commit-config.yaml") |  |  |
| [.readthedocs.yaml](/akfamily/akshare/blob/main/.readthedocs.yaml ".readthedocs.yaml") | | [.readthedocs.yaml](/akfamily/akshare/blob/main/.readthedocs.yaml ".readthedocs.yaml") |  |  |
| [CODE\_OF\_CONDUCT.md](/akfamily/akshare/blob/main/CODE_OF_CONDUCT.md "CODE_OF_CONDUCT.md") | | [CODE\_OF\_CONDUCT.md](/akfamily/akshare/blob/main/CODE_OF_CONDUCT.md "CODE_OF_CONDUCT.md") |  |  |
| [CONTRIBUTING.md](/akfamily/akshare/blob/main/CONTRIBUTING.md "CONTRIBUTING.md") | | [CONTRIBUTING.md](/akfamily/akshare/blob/main/CONTRIBUTING.md "CONTRIBUTING.md") |  |  |
| [Dockerfile](/akfamily/akshare/blob/main/Dockerfile "Dockerfile") | | [Dockerfile](/akfamily/akshare/blob/main/Dockerfile "Dockerfile") |  |  |
| [Dockerfile-Jupyter](/akfamily/akshare/blob/main/Dockerfile-Jupyter "Dockerfile-Jupyter") | | [Dockerfile-Jupyter](/akfamily/akshare/blob/main/Dockerfile-Jupyter "Dockerfile-Jupyter") |  |  |
| [LICENSE](/akfamily/akshare/blob/main/LICENSE "LICENSE") | | [LICENSE](/akfamily/akshare/blob/main/LICENSE "LICENSE") |  |  |
| [README.md](/akfamily/akshare/blob/main/README.md "README.md") | | [README.md](/akfamily/akshare/blob/main/README.md "README.md") |  |  |
| [pyproject.toml](/akfamily/akshare/blob/main/pyproject.toml "pyproject.toml") | | [pyproject.toml](/akfamily/akshare/blob/main/pyproject.toml "pyproject.toml") |  |  |
| [setup.py](/akfamily/akshare/blob/main/setup.py "setup.py") | | [setup.py](/akfamily/akshare/blob/main/setup.py "setup.py") |  |  |
| View all files | | |

## Latest commit

## History

## Repository files navigation

**资源分享**：对于想了解更多财经数据与量化投研的小伙伴，推荐一个专注于财经数据和量化研究的知识社区。
该社区提供相关文档和视频学习资源，汇集了各类财经数据源和量化投研工具的使用经验。
有兴趣深入学习的朋友可点此[了解更多](https://t.zsxq.com/ZCxUG)，也推荐大家关注微信公众号【数据科学实战】。

**重磅推荐**：AKQuant 是一款专为 **量化投研 (Quantitative Research)** 打造的高性能量化回测框架。它以 Rust 铸造极速撮合内核，
以 Python 链接数据与 AI 生态，旨在为量化投资者提供可靠高效的量化投研解决方案。参见[AKQuant](https://github.com/akfamily/akquant)

**工具推荐**：期魔方是一款本地化期货量化分析工具，适合数据分析爱好者使用。无需复杂部署，支持数据分析和机器学习功能，研究功能免费开放。
如需了解更多信息可访问[期魔方](https://qmfquant.com)。

[![AKShare Logo](https://github.com/akfamily/akshare/raw/main/assets/images/akshare_logo.jpg)](https://github.com/akfamily/akshare/blob/main/assets/images/akshare_logo.jpg)

![AKShare Logo](https://github.com/akfamily/akshare/raw/main/assets/images/akshare_logo.jpg)

[![PyPI - Python Version](https://camo.githubusercontent.com/6525815d69cd8f142bbddb9fedb1f25dd8319a33d411e74c72d326d9eaa5c6f5/68747470733a2f2f696d672e736869656c64732e696f2f707970692f707976657273696f6e732f616b73686172652e737667)](https://pypi.org/project/akshare/)
[![PyPI](https://camo.githubusercontent.com/1748087edf808c73b210dbe9510a3174ee9441d1fd5dcde62e97a53dc98cbea6/68747470733a2f2f696d672e736869656c64732e696f2f707970692f762f616b73686172652e737667)](https://pypi.org/project/akshare/)
[![PyPI Downloads](https://camo.githubusercontent.com/92f8c559e6b1a5ab17f32434f660aac80e479f605ae1ae713d552f9c7fc13e82/68747470733a2f2f7374617469632e706570792e746563682f706572736f6e616c697a65642d62616467652f616b73686172653f706572696f643d746f74616c26756e6974733d494e5445524e4154494f4e414c5f53595354454d266c6566745f636f6c6f723d424c41434b2672696768745f636f6c6f723d475245454e266c6566745f746578743d646f776e6c6f616473)](https://pepy.tech/projects/akshare)
[![Documentation Status](https://camo.githubusercontent.com/1d98a37976f1778abcc84c48972b90ff182a2798080aabd0f097c37e61085149/68747470733a2f2f72656164746865646f63732e6f72672f70726f6a656374732f616b73686172652f62616467652f3f76657273696f6e3d6c6174657374)](https://akshare.readthedocs.io/?badge=latest)
[![Ruff](https://camo.githubusercontent.com/d6c7524504b7d886a9d34c11f44b9d31b2de1a579325b42e932744c4575a063b/68747470733a2f2f696d672e736869656c64732e696f2f656e64706f696e743f75726c3d68747470733a2f2f7261772e67697468756275736572636f6e74656e742e636f6d2f61737472616c2d73682f727566662f6d61696e2f6173736574732f62616467652f76322e6a736f6e)](https://github.com/astral-sh/ruff)
[![akshare](https://camo.githubusercontent.com/140cc9437f1583f65292399d968313e01a5692984ff4be1a97878240a34aa498/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f44617461253230536369656e63652d414b53686172652d677265656e)](https://github.com/akfamily/akshare)
[![Actions Status](https://github.com/akfamily/akshare/actions/workflows/release_and_deploy.yml/badge.svg)](https://github.com/akfamily/akshare/actions)
[![MIT Licence](https://camo.githubusercontent.com/b8cadaa967891081f8f165695470689986c028821dd8a040132f6e661795dc0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d626c7565)](https://github.com/akfamily/akshare/blob/main/LICENSE)
[![](https://camo.githubusercontent.com/27efba95deaaf637fe264fbdf3b7b5fd962698a07544341b2e6d55b7b761c5bc/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f666f726b732f6a696e64617869616e672f616b7368617265)](https://github.com/akfamily/akshare)
[![](https://camo.githubusercontent.com/2a0a5f25fba98530c7af08bfb6f921715b96a9712e1331d3cdcade3d13355fb5/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f73746172732f6a696e64617869616e672f616b7368617265)](https://github.com/akfamily/akshare)
[![](https://camo.githubusercontent.com/ec586496426f8b7e4f7e744a54a5f89d7a404081007d896b4470747fda40e8be/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f6973737565732f6a696e64617869616e672f616b7368617265)](https://github.com/akfamily/akshare)
[![code style: prettier](https://camo.githubusercontent.com/fa1096c501361805c36b519890a25f61cd45dde376718bb2f5af65a656f4c0fa/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f636f64655f7374796c652d70726574746965722d6666363962342e7376673f7374796c653d666c61742d737175617265)](https://github.com/prettier/prettier)

![PyPI - Python Version](https://camo.githubusercontent.com/6525815d69cd8f142bbddb9fedb1f25dd8319a33d411e74c72d326d9eaa5c6f5/68747470733a2f2f696d672e736869656c64732e696f2f707970692f707976657273696f6e732f616b73686172652e737667)
![PyPI](https://camo.githubusercontent.com/1748087edf808c73b210dbe9510a3174ee9441d1fd5dcde62e97a53dc98cbea6/68747470733a2f2f696d672e736869656c64732e696f2f707970692f762f616b73686172652e737667)
![PyPI Downloads](https://camo.githubusercontent.com/92f8c559e6b1a5ab17f32434f660aac80e479f605ae1ae713d552f9c7fc13e82/68747470733a2f2f7374617469632e706570792e746563682f706572736f6e616c697a65642d62616467652f616b73686172653f706572696f643d746f74616c26756e6974733d494e5445524e4154494f4e414c5f53595354454d266c6566745f636f6c6f723d424c41434b2672696768745f636f6c6f723d475245454e266c6566745f746578743d646f776e6c6f616473)
![Documentation Status](https://camo.githubusercontent.com/1d98a37976f1778abcc84c48972b90ff182a2798080aabd0f097c37e61085149/68747470733a2f2f72656164746865646f63732e6f72672f70726f6a656374732f616b73686172652f62616467652f3f76657273696f6e3d6c6174657374)
![Ruff](https://camo.githubusercontent.com/d6c7524504b7d886a9d34c11f44b9d31b2de1a579325b42e932744c4575a063b/68747470733a2f2f696d672e736869656c64732e696f2f656e64706f696e743f75726c3d68747470733a2f2f7261772e67697468756275736572636f6e74656e742e636f6d2f61737472616c2d73682f727566662f6d61696e2f6173736574732f62616467652f76322e6a736f6e)
![akshare](https://camo.githubusercontent.com/140cc9437f1583f65292399d968313e01a5692984ff4be1a97878240a34aa498/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f44617461253230536369656e63652d414b53686172652d677265656e)
![Actions Status](https://github.com/akfamily/akshare/actions/workflows/release_and_deploy.yml/badge.svg)
![MIT Licence](https://camo.githubusercontent.com/b8cadaa967891081f8f165695470689986c028821dd8a040132f6e661795dc0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d626c7565)
![](https://camo.githubusercontent.com/27efba95deaaf637fe264fbdf3b7b5fd962698a07544341b2e6d55b7b761c5bc/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f666f726b732f6a696e64617869616e672f616b7368617265)
![](https://camo.githubusercontent.com/2a0a5f25fba98530c7af08bfb6f921715b96a9712e1331d3cdcade3d13355fb5/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f73746172732f6a696e64617869616e672f616b7368617265)
![](https://camo.githubusercontent.com/ec586496426f8b7e4f7e744a54a5f89d7a404081007d896b4470747fda40e8be/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f6973737565732f6a696e64617869616e672f616b7368617265)
![code style: prettier](https://camo.githubusercontent.com/fa1096c501361805c36b519890a25f61cd45dde376718bb2f5af65a656f4c0fa/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f636f64655f7374796c652d70726574746965722d6666363962342e7376673f7374796c653d666c61742d737175617265)

## Overview

[AKShare](https://github.com/akfamily/akshare) requires Python(64 bit) 3.9 or higher and
aims to simplify the process of fetching financial data.

**Write less, get more!**

## Installation

### General

### China

### PR

Please check out [Documentation](https://akshare.akfamily.xyz/contributing.html) if you
want to contribute to AKShare

### Docker

#### Pull images

#### Run Container

#### Test

## Usage

### Data

Code:

Output:

 `日期 开盘 收盘 最高 ... 振幅 涨跌幅 涨跌额 换手率
0 2017-03-01 9.49 9.49 9.55 ... 0.84 0.11 0.01 0.21
1 2017-03-02 9.51 9.43 9.54 ... 1.26 -0.63 -0.06 0.24
2 2017-03-03 9.41 9.40 9.43 ... 0.74 -0.32 -0.03 0.20
3 2017-03-06 9.40 9.45 9.46 ... 0.74 0.53 0.05 0.24
4 2017-03-07 9.44 9.45 9.46 ... 0.63 0.00 0.00 0.17
... ... ... ... ... ... ... ... ...
1610 2023-10-16 11.00 11.01 11.03 ... 0.73 0.09 0.01 0.26
1611 2023-10-17 11.01 11.02 11.05 ... 0.82 0.09 0.01 0.25
1612 2023-10-18 10.99 10.95 11.02 ... 1.00 -0.64 -0.07 0.34
1613 2023-10-19 10.91 10.60 10.92 ... 3.01 -3.20 -0.35 0.61
1614 2023-10-20 10.55 10.60 10.67 ... 1.51 0.00 0.00 0.27
[1615 rows x 11 columns]`

### Plot

Code:

Output:

[![KLine](https://camo.githubusercontent.com/c060f5ade8a1b35704c2416c14fce8499362232d97ec58eb82f05fcb6bf1d5bc/68747470733a2f2f6a6664732d313235323935323531372e636f732e61702d6368656e6764752e6d7971636c6f75642e636f6d2f616b73686172652f726561646d652f686f6d652f4141504c5f63616e646c652e706e67)](https://camo.githubusercontent.com/c060f5ade8a1b35704c2416c14fce8499362232d97ec58eb82f05fcb6bf1d5bc/68747470733a2f2f6a6664732d313235323935323531372e636f732e61702d6368656e6764752e6d7971636c6f75642e636f6d2f616b73686172652f726561646d652f686f6d652f4141504c5f63616e646c652e706e67)

![KLine](https://camo.githubusercontent.com/c060f5ade8a1b35704c2416c14fce8499362232d97ec58eb82f05fcb6bf1d5bc/68747470733a2f2f6a6664732d313235323935323531372e636f732e61702d6368656e6764752e6d7971636c6f75642e636f6d2f616b73686172652f726561646d652f686f6d652f4141504c5f63616e646c652e706e67)

## Features

## Tutorials

## Contribution

[AKShare](https://github.com/akfamily/akshare) is still under developing, feel free to open issues and pull requests:

Notice: We use [Ruff](https://github.com/astral-sh/ruff) to format the code

## Statement

## Show your style

Use the badge in your project's README.md:

Using the badge in README.rst:

`.. image:: https://img.shields.io/badge/Data%20Science-AKShare-green
:target: https://github.com/akfamily/akshare`

Looks like this:

[![Data: akshare](https://camo.githubusercontent.com/140cc9437f1583f65292399d968313e01a5692984ff4be1a97878240a34aa498/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f44617461253230536369656e63652d414b53686172652d677265656e)](https://github.com/akfamily/akshare)

![Data: akshare](https://camo.githubusercontent.com/140cc9437f1583f65292399d968313e01a5692984ff4be1a97878240a34aa498/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f44617461253230536369656e63652d414b53686172652d677265656e)

## Citation

Please use this **bibtex** if you want to cite this repository in your publications:

## Acknowledgement

Special thanks [FuShare](https://github.com/LowinLi/fushare) for the opportunity of learning from the project;

Special thanks [TuShare](https://github.com/waditu/tushare) for the opportunity of learning from the project;

Thanks for the data provided by [东方财富网站](http://data.eastmoney.com);

Thanks for the data provided by [新浪财经网站](https://finance.sina.com.cn);

Thanks for the data provided by [金十数据网站](https://www.jin10.com/);

Thanks for the data provided by [生意社网站](http://www.100ppi.com/);

Thanks for the data provided by [中国银行间市场交易商协会网站](http://www.nafmii.org.cn/);

Thanks for the data provided by [99期货网站](http://www.99qh.com/);

Thanks for the data provided by [中国外汇交易中心暨全国银行间同业拆借中心网站](http://www.chinamoney.com.cn/chinese/);

Thanks for the data provided by [和讯财经网站](http://www.hexun.com/);

Thanks for the data provided by [DACHENG-XIU 网站](https://dachxiu.chicagobooth.edu/);

Thanks for the data provided by [上海证券交易所网站](http://www.sse.com.cn/assortment/options/price/);

Thanks for the data provided by [深证证券交易所网站](http://www.szse.cn/);

Thanks for the data provided by [北京证券交易所网站](http://www.bse.cn/);

Thanks for the data provided by [中国金融期货交易所网站](http://www.cffex.com.cn/);

Thanks for the data provided by [上海期货交易所网站](http://www.shfe.com.cn/);

Thanks for the data provided by [大连商品交易所网站](http://www.dce.com.cn/);

Thanks for the data provided by [郑州商品交易所网站](http://www.czce.com.cn/);

Thanks for the data provided by [上海国际能源交易中心网站](http://www.ine.com.cn/);

Thanks for the data provided by [Timeanddate 网站](https://www.timeanddate.com/);

Thanks for the data provided by [河北省空气质量预报信息发布系统网站](http://110.249.223.67/publish/);

Thanks for the data provided by [Economic Policy Uncertainty 网站](http://www.nanhua.net/nhzc/varietytrend.html);

Thanks for the data provided by [申万指数网站](http://www.swsindex.com/idx0120.aspx?columnid=8832);

Thanks for the data provided by [真气网网站](https://www.zq12369.com/);

Thanks for the data provided by [财富网站](http://www.fortunechina.com/);

Thanks for the data provided by [中国证券投资基金业协会网站](http://gs.amac.org.cn/);

Thanks for the data provided by [Expatistan 网站](https://www.expatistan.com/cost-of-living);

Thanks for the data provided by [北京市碳排放权电子交易平台网站](https://www.bjets.com.cn/article/jyxx/);

Thanks for the data provided by [国家金融与发展实验室网站](http://www.nifd.cn/);

Thanks for the data provided by [义乌小商品指数网站](http://www.ywindex.com/Home/Product/index/);

Thanks for the data provided by [百度迁徙网站](https://qianxi.baidu.com/?from=shoubai#city=0);

Thanks for the data provided by [思知网站](https://www.ownthink.com/);

Thanks for the data provided by [Currencyscoop 网站](https://currencyscoop.com/);

Thanks for the data provided by [新加坡交易所网站](https://www.sgx.com/zh-hans/research-education/derivatives);

## About

AKShare is an elegant and simple financial data interface library for Python, built for human beings! 开源财经数据接口库

### Topics

### Resources

### License

### Code of conduct

### Contributing

### Uh oh!

There was an error while loading. Please reload this page.

There was an error while loading. Please reload this page.

### Stars

### Watchers

### Forks

## [Releases 185](/akfamily/akshare/releases)

### Uh oh!

There was an error while loading. Please reload this page.

There was an error while loading. Please reload this page.

## [Contributors](/akfamily/akshare/graphs/contributors)

### Uh oh!

There was an error while loading. Please reload this page.

There was an error while loading. Please reload this page.

## Languages

## Footer

### Footer navigation
