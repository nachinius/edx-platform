(function(define) {
'use strict';
// VideoEventsPlugin module.
define(
'video/09_events_plugin.js', [],
function() {
    /**
     * Video volume control module.
     * @exports video/09_events_plugin.js
     * @constructor
     * @param {Object} state The object containing the state of the video
     * @param {Object} i18n The object containing strings with translations.
     * @return {jquery Promise}
     */
    var EventsPlugin = function(state, i18n) {
        if (!(this instanceof EventsPlugin)) {
            return new EventsPlugin(state, i18n);
        }

        _.bindAll(this, 'onReady', 'onPlay', 'onPause', 'onEnded', 'onSeek',
            'onSpeedChange', 'onShowLanguageMenu', 'onHideLanguageMenu',
            'onShowCaptions', 'onHideCaptions', 'destroy');
        this.state = state;
        this.state.videoEventsPlugin = this;
        this.i18n = i18n;
        this.initialize();

        return $.Deferred().resolve().promise();
    };

    EventsPlugin.prototype = {
        destroy: function () {
            this.state.el.off({
                'ready': this.onReady,
                'play': this.onPlay,
                'pause': this.onPause,
                'ended': this.onEnded,
                'seek': this.onSeek,
                'speedchange': this.onSpeedChange,
                'language_menu:show': this.onShowLanguageMenu,
                'language_menu:hide': this.onHideLanguageMenu,
                'captions:show': this.onShowCaptions,
                'captions:hide': this.onHideCaptions,
                'destroy': this.destroy
            });
            delete this.state.videoEventsPlugin;
        },

        /** Initializes the module. */
        initialize: function() {
            this.bindHandlers();
        },

        /** Bind any necessary function callbacks to DOM events. */
        bindHandlers: function() {
            this.state.el.on({
                'ready': this.onReady,
                'play': this.onPlay,
                'pause': this.onPause,
                'ended': this.onEnded,
                'seek': this.onSeek,
                'speedchange': this.onSpeedChange,
                'language_menu:show': this.onShowLanguageMenu,
                'language_menu:hide': this.onHideLanguageMenu,
                'captions:show': this.onShowCaptions,
                'captions:hide': this.onHideCaptions,
                'destroy': this.destroy
            });
        },

        onReady: function () {
            this.log('load_video');
        },

        onPlay: function () {
            this.log('play_video', {currentTime: this.getCurrentTime()});
        },

        onPause: function () {
            this.log('pause_video', {currentTime: this.getCurrentTime()});
        },

        onEnded: function () {
            this.log('stop_video', {currentTime: this.getCurrentTime()});
        },

        onSeek: function (event, time, oldTime, type) {
            this.log('seek_video', {
                old_time: oldTime,
                new_time: time,
                type: type
            });
        },

        onSpeedChange: function (event, newSpeed, oldSpeed) {
            this.log('speed_change_video', {
                current_time: this.getCurrentTime(),
                old_speed: oldSpeed,
                new_speed: newSpeed
            });
        },

        onShowLanguageMenu: function () {
            this.log('video_show_cc_menu');
        },

        onHideLanguageMenu: function () {
            this.log('video_hide_cc_menu');
        },

        onShowCaptions: function () {
            this.log('show_transcript', {current_time: this.getCurrentTime()});
        },

        onHideCaptions: function () {
            this.log('hide_transcript', {current_time: this.getCurrentTime()});
        },

        getCurrentTime: function () {
            var player = this.state.videoPlayer;
            return player ? player.currentTime : 0;
        },

        log: function (eventName, data) {
            var logInfo = _.extend({
                id: this.state.id,
                code: this.state.isYoutubeType() ? this.state.youtubeId() : 'html5'
            }, data);
            Logger.log(eventName, logInfo);
        }

    };

    return EventsPlugin;
});
}(RequireJS.define));