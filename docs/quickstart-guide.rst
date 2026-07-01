.. _quickstart_guide:

=========================
DejaCode Quickstart Guide
=========================

Introduction
============
The goal of this quickstart guide is to help you get into DejaCode quickly, and give you a foundational understanding of core functionality.

For the sake of simplicity, this guide will assume you are using the nexB-hosted Private Evaluation version of DejaCode. If you'd prefer to self-host DejaCode, please follow `our installation guide here <https://dejacode.readthedocs.io/en/latest/installation.html>`_.

Accessing DejaCode
==================
To get your own Private Evaluation instance of DejaCode, you first need to request access:

1. Go to https://public.dejacode.com/account/register/
2. Select the 'Private Evaluation' tab
3. Fill in the form fields
4. Click 'Create account'
5. Click the activation link in your email

Now you should be able to `log in here <https://public.dejacode.com/login/>`_ with the credentials you entered.

Understanding the sections
==========================

Products
--------
A `Product <https://public.dejacode.com/products/>`_ represents a specific software project or application. So once you've created a Product for your software, this is where you manage its open-source components, licenses, and compliance status.

Essentially, this is where you get the detailed view of your software, and can identify where there might be risks or issues.

For example, if you open the DejaCode product entry, you'll see tabs across the top where you can access the different information stored against that product, such as Inventory, License, and Vulnerabilities.

Components
----------
A `Component <https://public.dejacode.com/components/>`_ refers to the individual open-source or third-party software elements (library, framework, tool, etc). Each component will have key details such as name, version, license type, and owner.

Essentially, components are building blocks which are added to products, such as React.js in a web app.

Packages
--------
A `Package <https://public.dejacode.com/packages/>`_ represents a bundled version of a software component in a format ready for distribution or deployment (.deb, .rpm, .npm, etc.). It includes metadata like version, license, dependencies, and source code links, helping you to track exact releases used in your products.

DejaCode analyzes these packages in order to identify compliance risks, security vulnerabilities, and license conflicts. Combined with components, you're able to maintain precise control over dependencies across your software supply chain.

Licenses
--------
A `License <https://public.dejacode.com/licenses/>`_ in DejaCode is exactly what it sounds like — the legal terms and conditions under which an open-source or third-party component can be used, modified, or distributed. Each license is categorized and linked to its associated component. This makes it possible for DejaCode to automatically check for compliance, track obligations, and flag conflicts.

This means you can centralize your license data, streamlining things like approvals, audits, and reporting across your different products.

Owners
------
An `Owner <https://public.dejacode.com/owners/>`_ is the individual, team, or organization responsible for managing and maintaining specific components, packages, or products within the system. This is to track accountability, streamline decision-making, and ensure proper oversight of compliance, licensing, and security issues.

Tools
-----
DejaCode comes with several important tools built-in, including `reports <https://dejacode.readthedocs.io/en/latest/tutorial-3.html>`_, a `vulnerability search <https://dejacode.readthedocs.io/en/latest/tutorial-4-vulnerabilities.html>`_, and an API browser. These are all to make it easier for you to have clear oversight of your products and all of their components.

Next: `Tutorial 1 - Your first Product <https://dejacode.readthedocs.io/en/latest/tutorial-1.html>`_