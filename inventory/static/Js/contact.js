$(document).ready(function () {
    $("#contact-form").submit(function (event) {
        event.preventDefault();

        let formData = {
            name: $("#name").val(),
            email: $("#email").val(),
            phone: $("#phone").val(),
            query: $("#query").val(),
            response_type: $("#response_type").val()
        };

        $.post("/submit_query/", formData, function (response) {
            $("#response-message").text(response.message);
            $("#contact-form")[0].reset();
        });
    });
});