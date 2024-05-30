====================
Document Maintenance
====================

Document Software Setup
=======================

The DejaCode User Guide is built using Sphinx.
See http://www.sphinx-doc.org/en/master/index.html

Individual document files are in reStructuredText format.
See http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html

You create, build, and preview DejaCode documentation on your local machine.

You commit your updates to the DejaCode repository on GitHub.

Clone DejaCode
==============

To get started, create or identify a working directory on your local machine.

Open that directory and execute the following command in a terminal session::

    git clone https://github.com/nexB/dejacode.git

That will create a /dejacode directory in your working directory.
Now you can install the dependencies in a virtualenv::

    cd dejacode
    python3.12 -m venv .
    source bin/activate

Now you can build the HTML documents locally::

    make html

Assuming that your Sphinx installation was successful, Sphinx should build a
local instance of the documentation .html files::

    open docs/build/html/index.html

You now have a local build of the DejaCode documents.

Format and style
================

Use the following tags to highlight elements of the documentation:

- Button/Link: :guilabel:`Click here`
- Value: ``value``
- Field: **Field Name**

Improve DejaCode Documents
==========================

Before you begin creating and modifying DejaCode documents, be sure that you
understand the basics of reStructuredText as explained at
http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html

Ensure that you have the latest DejaCode files::

    git pull
    git status

Use your favorite text editor to create and modify .rst files to make your
documentation improvements.

Review your work::

    make html
    open docs/build/html/index.html

Share DejaCode Document Improvements
====================================

Follow standard git procedures to upload your new and modified files.
The following commands are examples::

    git status
    git add source/index.rst
    git add source/how-to-scan.rst
    git status
    git commit -m "New how-to document that explains how to scan"
    git status
    git push
    git status

To be continued ...
