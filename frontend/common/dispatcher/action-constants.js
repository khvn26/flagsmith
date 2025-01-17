const Actions = Object.assign({}, require('./base/_action-constants'), {
    'ACCEPT_INVITE': 'ACCEPT_INVITE',
    'CHANGE_USER_FLAG': 'CHANGE_USER_FLAG',
    'CREATE_ENV': 'CREATE_ENV',
    'CREATE_FLAG': 'CREATE_FLAG',
    'CREATE_ORGANISATION': 'CREATE_ORGANISATION',
    'CREATE_PROJECT': 'CREATE_PROJECT',
    'DELETE_ENVIRONMENT': 'DELETE_ENVIRONMENT',
    'DELETE_IDENTITY_TRAIT': 'DELETE_IDENTITY_TRAIT',
    'DELETE_INVITE': 'DELETE_INVITE',
    'DELETE_USER': 'DELETE_USER',
    'DELETE_ORGANISATION': 'DELETE_ORGANISATION',
    'MIGRATE_PROJECT': 'MIGRATE_PROJECT',
    'CREATE_GROUP': 'CREATE_GROUP',
    'GET_GROUPS': 'GET_GROUPS',
    'GET_GROUPS_PAGE': 'GET_GROUPS_PAGE',
    'DELETE_GROUP': 'DELETE_GROUP',
    'UPDATE_GROUP': 'UPDATE_GROUP',
    'DELETE_PROJECT': 'DELETE_PROJECT',
    'EDIT_ENVIRONMENT': 'EDIT_ENVIRONMENT',
    'EDIT_ENVIRONMENT_FLAG': 'EDIT_ENVIRONMENT_FLAG',
    'EDIT_ENVIRONMENT_FLAG_CHANGE_REQUEST': 'EDIT_ENVIRONMENT_FLAG_CHANGE_REQUEST',
    'EDIT_FEATURE': 'EDIT_FEATURE',
    'EDIT_FEATURE_MV': 'EDIT_FEATURE_MV',
    'EDIT_ORGANISATION': 'EDIT_ORGANISATION',
    'EDIT_PROJECT': 'EDIT_PROJECT',
    'EDIT_TRAIT': 'EDIT_TRAIT',
    'EDIT_USER_FLAG': 'EDIT_USER_FLAG',
    'GET_ENVIRONMENT': 'GET_ENVIRONMENT',
    'GET_FLAGS': 'GET_FLAGS',
    'SEARCH_FLAGS': 'SEARCH_FLAGS',
    'GET_CHANGE_REQUESTS': 'GET_CHANGE_REQUESTS',
    'GET_CHANGE_REQUEST': 'GET_CHANGE_REQUEST',
    'UPDATE_CHANGE_REQUEST': 'UPDATE_CHANGE_REQUEST',
    'DELETE_CHANGE_REQUEST': 'DELETE_CHANGE_REQUEST',
    'ACTION_CHANGE_REQUEST': 'ACTION_CHANGE_REQUEST',
    'GET_IDENTITY': 'GET_IDENTITY',
    'GET_IDENTITY_SEGMENTS': 'GET_IDENTITY_SEGMENTS',
    'GET_ORGANISATION': 'GET_ORGANISATION',
    'OAUTH': 'OAUTH',
    'GET_PROJECT': 'GET_PROJECT',
    'INVITE_USERS': 'INVITE_USERS',
    'INVALIDATE_INVITE_LINK': 'INVALIDATE_INVITE_LINK',
    'REMOVE_FLAG': 'REMOVE_FLAG',
    'REMOVE_USER_FLAG': 'REMOVE_USER_FLAG',
    'RESEND_INVITE': 'RESEND_INVITE',
    'SELECT_ENVIRONMENT': 'SELECT_ENVIRONMENT',
    'SELECT_ORGANISATION': 'SELECT_ORGANISATION',
    'ENABLE_TWO_FACTOR': 'ENABLE_TWO_FACTOR',
    'DISABLE_TWO_FACTOR': 'DISABLE_TWO_FACTOR',
    'CONFIRM_TWO_FACTOR': 'CONFIRM_TWO_FACTOR',
    'TWO_FACTOR_LOGIN': 'TWO_FACTOR_LOGIN',
    'TOGGLE_FLAG': 'TOGGLE_FLAG',
    'TOGGLE_USER_FLAG': 'TOGGLE_USER_FLAG',
    'UPDATE_USER_ROLE': 'UPDATE_USER_ROLE',
    'UPDATE_SUBSCRIPTION': 'UPDATE_SUBSCRIPTION',
    'GET_FLAG_INFLUX_DATA': 'GET_FLAG_INFLUX_DATA',
    'REFRESH_FEATURES': 'REFRESH_FEATURES',
});

window.Actions = Actions;
module.exports = Actions;
