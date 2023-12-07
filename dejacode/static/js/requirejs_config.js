define([], function () {
    requirejs.config({
        waitSeconds: 60,
        baseUrl: '/static',
        paths: {
            'nexb': 'js/nexb',
            'jquery': 'js/jquery-1.12.4.min',
            // Depend on the copy of jQuery UI from Grappelli
            'jqueryui': 'grappelli/jquery/ui/jquery-ui',
            'ember-template-compiler': 'js/ember/ember-template-compiler-1.12.1',
            'ember': 'js/ember/ember-1.12.1.min',
            'underscore': 'js/underscore-min',
            'underscore.string': 'js/underscore.string.min',
            'text': 'js/text'
        },
        shim: {
            'jqueryui': {
                deps: ['jquery']
            },
            'underscore': {
                exports: '_'
            },
            'ember': {
                deps: ['jquery'],
                exports: 'Ember'
            }
        }
    });
});
