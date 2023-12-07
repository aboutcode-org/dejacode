// This file is based on tags.coffee of Annotator.  The input type was changed
// to "select".  The regular expression was changed in `parseTags()` so that tag
// values are not split on whitespace characters.

var __bind = function(fn, me){ return function(){ return fn.apply(me, arguments); }; },
  __hasProp = Object.prototype.hasOwnProperty,
  __extends = function(child, parent) { for (var key in parent) { if (__hasProp.call(parent, key)) child[key] = parent[key]; } function ctor() { this.constructor = child; } ctor.prototype = parent.prototype; child.prototype = new ctor; child.__super__ = parent.prototype; return child; };

Annotator.Plugin.TagsInSelect = (function(_super) {

  __extends(TagsInSelect, _super);

  function TagsInSelect(element, options) {
    if (! options || ! options.values) {
        throw Error('``values`` must be passed');
    }
    this.setAnnotationTags = __bind(this.setAnnotationTags, this);
    this.updateField = __bind(this.updateField, this);
    TagsInSelect.__super__.constructor.apply(this, arguments);
  }

  TagsInSelect.prototype.options = {
    parseTags: function(string) {
      var tags;
      string = $.trim(string);
      tags = [];
      if (string) tags = string.split(/\s*,\s*/);
      return tags;
    },
    stringifyTags: function(array) {
      return array.join(" ");
    }
  };

  TagsInSelect.prototype.field = null;

  TagsInSelect.prototype.input = null;

  TagsInSelect.prototype.pluginInit = function() {
    if (!Annotator.supported()) return;
    this.field = this.annotator.editor.addField({
      type: 'select',
      label: Annotator._t('Add some tags here') + '\u2026',
      load: this.updateField,
      submit: this.setAnnotationTags
    });
    this.annotator.viewer.addField({
      load: this.updateViewer
    });
    if (this.annotator.plugins.Filter) {
      this.annotator.plugins.Filter.addFilter({
        label: Annotator._t('Tag'),
        property: 'tags',
        isFiltered: Annotator.Plugin.TagsInSelect.filterCallback
      });
    }
    this.input = $(this.field).find(':input');
    this.input.append("<option value=''>Select any tag...</option>");
    for (var i = 0, len = this.options.values.length; i < len; i++) {
      var label = this.options.values[i];
      this.input.append("<option value='" + label + "'>" + label + "</option>");
    }
    return this.input;
  };

  TagsInSelect.prototype.parseTags = function(string) {
    return this.options.parseTags(string);
  };

  TagsInSelect.prototype.stringifyTags = function(array) {
    return this.options.stringifyTags(array);
  };

  TagsInSelect.prototype.updateField = function(field, annotation) {
    var value;
    value = '';
    if (annotation.tags) value = this.stringifyTags(annotation.tags);
    return this.input.val(value);
  };

  TagsInSelect.prototype.setAnnotationTags = function(field, annotation) {
    return annotation.tags = this.parseTags(this.input.val());
  };

  TagsInSelect.prototype.updateViewer = function(field, annotation) {
    field = $(field);
    if (annotation.tags && $.isArray(annotation.tags) && annotation.tags.length) {
      return field.addClass('annotator-tags').html(function() {
        var string;
        return string = $.map(annotation.tags, function(tag) {
          return '<span class="annotator-tag">' + Annotator.Util.escape(tag) + '</span>';
        }).join(' ');
      });
    } else {
      return field.remove();
    }
  };

  return TagsInSelect;

})(Annotator.Plugin);

Annotator.Plugin.TagsInSelect.filterCallback = function(input, tags) {
  var keyword, keywords, matches, tag, _i, _j, _len, _len2;
  if (tags == null) tags = [];
  matches = 0;
  keywords = [];
  if (input) {
    keywords = input.split(/\s+/g);
    for (_i = 0, _len = keywords.length; _i < _len; _i++) {
      keyword = keywords[_i];
      if (tags.length) {
        for (_j = 0, _len2 = tags.length; _j < _len2; _j++) {
          tag = tags[_j];
          if (tag.indexOf(keyword) !== -1) matches += 1;
        }
      }
    }
  }
  return matches === keywords.length;
};
