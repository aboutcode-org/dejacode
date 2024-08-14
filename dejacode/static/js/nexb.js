/*
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#
*/
define([
  "jquery",
  "ember",
  "underscore.string",
  "ember-template-compiler",
], function ($, Ember, _s) {
  var App = Ember.Application.create();
  window.App = App;

  App.client_data = Ember.Object.create(NEXB.client_data);

  var TemplatedViewController = Ember.Object.extend({
    templateFunction: null,
    viewArgs: null,
    viewBaseClass: Ember.View,
    view: function () {
      var controller = this;
      var viewArgs = this.get("viewArgs") || {};
      var args = {
        template: controller.get("templateFunction"),
        controller: controller,
      };
      args = $.extend(viewArgs, args);
      return this.get("viewBaseClass").extend(args);
    }.property("templateFunction", "viewArgs"),
    appendView: function (selector) {
      this.get("view").create().appendTo(selector);
    },
    appendViewToBody: function () {
      this.get("view").create().append();
    },
    appendPropertyViewToBody: function (property) {
      this.get(property).create().append();
    },
  });

  var FocusedTextField = Ember.TextField.extend({
    didInsertElement: function () {
      var that = this;
      // Connect ``focusoutCallback()``
      this.$().focusout(function () {
        that.focusoutCallback();
      });
      // Focus the text field in a separate run loop otherwise the text won't be in focus
      Ember.run.next(this, function () {
        this.$().focus();
      });
    },
    focusoutCallback: function () {},
  });

  var InlineForm = TemplatedViewController.extend({
    controller: null,
    view: function () {
      var controller = this;
      var viewArgs = this.get("viewArgs") || {};
      var args = {
        template: controller.get("templateFunction"),
        controller: controller,
      };
      var args2 = {
        tagName: "div",
        classNames: ["grp-module", "grp-tbody", "grp-dynamic-form"],
        classNameBindings: ["classes"],
        classes: function () {
          if (this.get("controller.predeleted")) {
            return "grp-predelete";
          }
          return "";
        }.property("controller.predeleted"),
        isVisibleBinding: "controller.isVisible",
      };
      args = $.extend(viewArgs, args, args2);
      return this.get("viewBaseClass").extend(args);
    }.property("templateFunction", "viewArgs"),
    formsetIndex: null,
    formsetPrefix: function () {
      return this.get("controller.formsetPrefix");
    }.property("controller.formsetPrefix"),
    initialData: null,
    isInitial: function () {
      // A form is an initial form if it has an id
      return this.get("idValue");
    }.property("idValue"),
    predeleted: false,
    deleteCheckbox: function () {
      var controller = this;
      return Ember.Checkbox.extend({
        controller: controller,
        checkedBinding: "controller.predeleted",
        attributeBindings: ["name", "style"],
        name: function () {
          var controller = this.get("controller");
          return _s.sprintf(
            "%s-%s-DELETE",
            controller.get("formsetPrefix"),
            controller.get("formsetIndex")
          );
        }.property(),
        // Do not display this checkbox since there are other UI
        // controls that delegate to this checkbox
        style: "display: none;",
      });
    }.property(),

    isVisible: true,
    makeInvisible: function () {
      this.set("isVisible", false);
    },
    makeVisible: function () {
      this.set("isVisible", true);
    },

    // Id
    idName: function () {
      return _s.sprintf(
        "%s-%s-id",
        this.get("formsetPrefix"),
        this.get("formsetIndex")
      );
    }.property("formsetPrefix", "formsetIndex"),
    idValue: function () {
      return this.get("initialData.pk");
    }.property("initialData"),

    // Actions
    removeForm: function () {
      this.get("controller").removeForm(this);
    },
    togglePredeletion: function () {
      var form = this;
      var predeleted = form.get("predeleted");
      if (predeleted) {
        form.set("predeleted", false);
      } else {
        form.set("predeleted", true);
      }
    },
  });

  var ContentTypeAwareInlineForm = InlineForm.extend({
    contentTypeBinding: "controller.contentType",
  });

  var Inline = TemplatedViewController.extend({
    init: function () {
      var that = this;
      var forms = [];
      var initialInlineData = this.getInitialInlineData();
      if (initialInlineData) {
        initialInlineData.forEach(function (item, index, enumerable) {
          var initialData = item;
          forms.pushObject(that.createForm({ initialData: initialData }));
        });
      }
      this.set("forms", forms);
      this.setFormsetIndexes();
    },
    formsetPrefix: null,
    forms: null,
    formsChanged: function () {
      this.setFormsetIndexes();
    }.observes("forms", "forms.[]"),
    formContainers: function () {
      var that = this;
      return this.get("forms").map(function (item, index, enumerable) {
        var form = item;
        return that.createFormContainer(form);
      });
    }.property("forms.[]"),
    createFormContainer: function (form) {
      // We use form container objects instead of passing an array of forms to the template directly because for whatever reason, this will not work:
      // {{#each forms}}
      //     {{view this.view}}
      // {{/each}}
      return Ember.Object.create({ form: form });
    },
    getInitialInlineData: function () {
      throw new Error("Subclass must implement");
    },
    getFormClass: function () {
      throw new Error("Subclass must implement");
    },
    getInitialForms: function () {
      var initialForms = [];
      this.get("forms").forEach(function (item, index, enumerable) {
        var form = item;
        if (form.get("isInitial")) {
          initialForms.pushObject(form);
        }
      });
      return initialForms;
    },
    createForm: function (args) {
      args = $.extend({ controller: this }, args);
      return this.getFormClass().create(args);
    },
    setFormsetIndexes: function () {
      this.get("forms").forEach(function (item, index, enumerable) {
        var form = item;
        form.set("formsetIndex", index);
      });
    },
    addForm: function () {
      this.get("forms").pushObject(this.createForm());
    },
    removeForm: function (formToBeRemoved) {
      var toRemove = [];
      var forms = this.get("forms");
      forms.forEach(function (item, index, enumerable) {
        var form = item;
        if (Ember.isEqual(form, formToBeRemoved)) {
          toRemove.pushObject(form);
        }
      });
      forms.removeObjects(toRemove);
    },
    totalFormCountName: function () {
      return _s.sprintf("%s-TOTAL_FORMS", this.get("formsetPrefix"));
    }.property(),
    totalFormCount: function () {
      return this.get("forms.length");
    }.property("forms.[]"),
    initialFormCountName: function () {
      return _s.sprintf("%s-INITIAL_FORMS", this.get("formsetPrefix"));
    }.property(),
    initialFormCount: null,
    hasErrors: null,
  });

  var ContentTypeAwareInline = Inline.extend({
    contentType: null,
    contentTypeMatchesContentTypeOfInitialForms: function () {
      var initialForms = this.getInitialForms();
      if (!Ember.isEmpty(initialForms)) {
        var contentTypeIdOfInitialForms =
          initialForms[0].initialData.content_type_id;
        var contentTypeOfInitialForms =
          App.client_data.content_type_map[contentTypeIdOfInitialForms];
        return contentTypeOfInitialForms === this.get("contentType");
      }
      return false;
    },
    contentTypeChanged: function () {
      var forms;
      if (this.get("contentType")) {
        var initialForms = this.getInitialForms();

        if (!this.contentTypeMatchesContentTypeOfInitialForms()) {
          initialForms.forEach(function (item, index, enumerable) {
            var form = item;
            form.set("predeleted", true);
            form.makeInvisible();
          });

          forms = initialForms;
        } else {
          initialForms.forEach(function (item, index, enumerable) {
            var form = item;
            form.set("predeleted", false);
            form.makeVisible();
          });

          forms = initialForms;
        }
      } else {
        forms = [];
      }

      this.get("forms").setObjects(forms);
    }.observes("contentType"),
  });

  var DraggableRowsInlineMixin = Ember.Mixin.create({
    viewBaseClass: function () {
      var controller = this;
      return Ember.View.extend({
        // ``originalIndex`` and ``newIndex`` are used to store values while dragging and dropping
        originalIndex: null,
        newIndex: null,
        getItemList: function () {
          var view = this;
          var items = view.$("div.grp-dynamic-form");
          return items;
        },
        getIndexOfItem: function (item) {
          return this.getItemList().index(item);
        },
        didInsertElement: function () {
          var view = this;
          view.$(".grp-group").sortable({
            handle: "a.grp-drag-handler",
            items: "div.grp-dynamic-form",
            axis: "y",
            appendTo: "body",
            forceHelperSize: true,
            placeholder: "grp-module",
            forcePlaceholderSize: true,
            tolerance: "pointer",
            containment: view.$(".grp-table"),
            start: function (event, ui) {
              var index = view.getIndexOfItem(ui.item);
              view.set("originalIndex", index);
              console.log(_s.sprintf("originalIndex: %s", index));
            },
            stop: function (event, ui) {
              var index = view.getIndexOfItem(ui.item);
              view.set("newIndex", index);
              console.log(_s.sprintf("newIndex: %s", index));

              controller.setSortableProperty(
                view.get("originalIndex"),
                view.get("newIndex")
              );

              // Clear index members
              view.set("originalIndex", null);
              view.set("newIndex", null);

              // HACK: Taken from Grappelli:
              // Toggle div.table twice to remove webkits border-spacing bug
              view.$("div.grp-table").toggle().toggle();
            },
          });
        },
      });
    }.property(),
    sortablePropertyName: null,
    getFormsInDraggedOrder: function (originalIndex, newIndex) {
      if (!this.get("sortablePropertyName")) {
        throw new Error("sortablePropertyName is not defined");
      }

      // Make a copy so that the original array is not modified
      var formsCopy = this.get("forms").copy();

      // Order by ``sortablePropertyName``
      formsCopy = formsCopy.sortBy(this.get("sortablePropertyName"));

      // Reorder the forms
      var reorderedItem = formsCopy[originalIndex];
      formsCopy.removeAt(originalIndex);
      formsCopy.insertAt(newIndex, reorderedItem);

      // Log
      var identifiers = formsCopy.map(function (item, index, enumerable) {
        var form = item;
        return form.getIdentifier();
      });
      console.log(identifiers);

      return formsCopy;
    },
    setSortableProperty: function (originalIndex, newIndex) {
      var inline = this;
      var forms = this.getFormsInDraggedOrder(originalIndex, newIndex);
      forms.forEach(function (item, index, enumerable) {
        var form = item;
        form.set(inline.get("sortablePropertyName"), index);
      });
    },
  });

  var FieldSelectorView = Ember.ContainerView.extend({
    controller: null,
    childViews: function () {
      var that = this;
      var controller = this.get("controller");
      var contentType = controller.get("contentType");
      var selectedFields = controller.get("selectedFields");

      var ret = [];

      if (!controller.get("isVisible")) {
        return ret;
      }

      if (!Ember.isEmpty(selectedFields)) {
        var model = contentType;
        selectedFields.forEach(function (item, index, enumerable) {
          var selection = item;
          if (selection && model) {
            var select = that
              .makeSelect(model, that.getPositionIndex(), selection)
              .create();
            ret.pushObject(select);
            if (_.has(App.client_data.model_data[model].meta, selection)) {
              model = App.client_data.model_data[model].meta[selection].model;
            } else {
              model = null;
            }
          }
        });

        // If ``model`` (which is represented by the last selected field) is defined then it is a foreign key.
        // If the last selected field is a foreign key, then there is one more select to add.
        if (model) {
          ret.pushObject(
            this.makeSelect(model, this.getPositionIndex()).create()
          );
        }
      } else {
        // It may be that no content type is selected
        if (contentType) {
          var select = this.makeSelect(
            contentType,
            this.getPositionIndex()
          ).create();
          ret.pushObject(select);
        }
      }

      return ret;
    }.property(),
    nextPositionIndex: 0,
    incrementPositionIndex: function () {
      this.set("nextPositionIndex", this.get("nextPositionIndex") + 1);
    },
    getPositionIndex: function () {
      var index = this.get("nextPositionIndex");
      this.incrementPositionIndex();
      return index;
    },
    setNextPositionIndex: function (newValue) {
      this.set("nextPositionIndex", newValue + 1);
    },
    makeSelect: function (modelName, positionIndex, selection) {
      var view = this;
      return Ember.Select.extend({
        positionIndex: positionIndex,
        content: App.client_data.model_data[modelName].grouped_fields,
        optionGroupPath: "group",
        optionLabelPath: "content.label",
        optionValuePath: "content.value",
        prompt: "---------",
        selection: function () {
          if (!selection) {
            return null;
          }

          var array = this.get("content").filterBy("value", selection);
          if (array.length !== 1) {
            console.log(_s.sprintf("Error with the value: %s", selection));
            return;
          }
          return array[0];
        }.property(),
        selectionChanged: function () {
          var selection = this.get("selection");

          // Remove child views after this one
          var lastIndex = view.get("length") - 1;
          if (lastIndex > this.get("positionIndex")) {
            view.removeAt(
              this.get("positionIndex") + 1,
              lastIndex - this.get("positionIndex")
            );
            view.setNextPositionIndex(this.get("positionIndex"));
          }

          if (
            selection &&
            _.has(
              App.client_data.model_data[modelName].meta,
              selection.value
            ) &&
            App.client_data.model_data[modelName].meta[selection.value].model
          ) {
            var relatedModel =
              App.client_data.model_data[modelName].meta[selection.value].model;
            console.log(_s.sprintf("relatedModel is %s", relatedModel));
            view.pushObject(
              view.makeSelect(relatedModel, view.getPositionIndex()).create()
            );
          }

          var selectedFields = [];
          view.get("childViews").forEach(function (item, index, enumerable) {
            var childView = item;
            var selection = childView.get("selection.value");
            selectedFields.pushObject(selection);
          });
          view
            .get("controller")
            .get("selectedFields")
            .setObjects(selectedFields);
          console.log(
            _s.sprintf(
              "selectedFields: %s",
              view.get("controller").get("selectedFields")
            )
          );
        }.observes("selection"),
      });
    },
  });

  return {
    App: App,
    TemplatedViewController: TemplatedViewController,
    FocusedTextField: FocusedTextField,
    InlineForm: InlineForm,
    ContentTypeAwareInlineForm: ContentTypeAwareInlineForm,
    Inline: Inline,
    ContentTypeAwareInline: ContentTypeAwareInline,
    DraggableRowsInlineMixin: DraggableRowsInlineMixin,
    FieldSelectorView: FieldSelectorView,
  };
});
