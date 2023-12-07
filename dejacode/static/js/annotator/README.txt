The following includes were commented for security reason, as it's loading
external resources.
The only purpose of those is for compatibility with some old IE version (<=8)
Our Annotator usage was tested fine without this in:
Chrome, Firefox, Opera, Safari, IE9+.
Note that we could consider to serve those external libraries ourself but we'll
have to consider the lgpl 3.0 license for xpath.min.js
See https://github.com/okfn/annotator/issues/85

Removed parts:

```
if(((_ref1=g.document)!=null?_ref1.evaluate:void 0)==null){$.getScript("http://assets.annotateit.org/vendor/xpath.min.js")}if(g.getSelection==null){$.getScript("http://assets.annotateit.org/vendor/ierange.min.js")}if(g.JSON==null){$.getScript("http://assets.annotateit.org/vendor/json2.min.js")}
```