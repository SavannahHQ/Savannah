jQuery('#id_auth_id').on('change', function() {
    if (this.value == 'other' ) {
        jQuery('#div_id_other').show();
    }
    else {
        jQuery('#div_id_other').hide();
    }
});

if (document.getElementById('id_auth_id').value != 'other') {
    jQuery('#div_id_other').hide();
}