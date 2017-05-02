/** funshion 自定义js */

// 此函数用于判断元素是否在数组内 
function contains(arr, obj) {  
    var i = arr.length;  
    while (i--) {  
        if (arr[i] === obj) {  
            return true;  
        }  
    }  
    return false;  
}
